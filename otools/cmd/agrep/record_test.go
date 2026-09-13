package main

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	mysql "github.com/go-sql-driver/mysql"
)

// fakeExecer implements sqlExecer with canned results/errors per call.
type fakeExecer struct {
	calls   []string
	handler func(query string) (sql.Result, error)
}

func (f *fakeExecer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	f.calls = append(f.calls, query)
	return f.handler(query)
}

type fakeResult int64

func (r fakeResult) LastInsertId() (int64, error) { return 0, nil }
func (r fakeResult) RowsAffected() (int64, error) { return int64(r), nil }

func dupErr() error { return &mysql.MySQLError{Number: 1062} }

func TestInsertRecordRetryOnDup(t *testing.T) {
	attempts := 0
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) {
		attempts++
		if attempts == 1 {
			return nil, dupErr()
		}
		return fakeResult(1), nil
	}}
	row := recordRow{SessionID: "s", MessageID: "m", Agent: "a", Path: "/p", Intent: "i"}
	if err := insertRecord(context.Background(), fe, row); err != nil {
		t.Fatalf("insertRecord: %v", err)
	}
	if attempts != 2 {
		t.Fatalf("attempts=%d, want 2 (retry after ER_DUP_ENTRY)", attempts)
	}
	if !strings.Contains(fe.calls[0], "COALESCE(MAX(turn_id), 0) + 1") {
		t.Fatalf("turn_id semantics missing: %s", fe.calls[0])
	}
}

func TestInsertRecordNonDupError(t *testing.T) {
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) {
		return nil, errors.New("connection lost")
	}}
	if err := insertRecord(context.Background(), fe, recordRow{}); err == nil {
		t.Fatal("want error")
	}
	if len(fe.calls) != 1 {
		t.Fatalf("non-dup error must not retry, calls=%d", len(fe.calls))
	}
}

func TestEnsureSchema(t *testing.T) {
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(0), nil }}
	if err := ensureSchema(context.Background(), fe); err != nil {
		t.Fatalf("ensureSchema: %v", err)
	}
	if len(fe.calls) != 2 {
		t.Fatalf("calls=%d, want 2 DDL statements", len(fe.calls))
	}
}

func TestClaimInject(t *testing.T) {
	// Slot claimed via UPDATE.
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(1), nil }}
	ok, err := claimInject(context.Background(), fe, "s", "p", "hint")
	if !ok || err != nil || len(fe.calls) != 1 {
		t.Fatalf("update path: ok=%v err=%v calls=%d", ok, err, len(fe.calls))
	}

	// No row yet -> INSERT succeeds.
	fe = &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(1), nil }}
	fe.handler = func(query string) (sql.Result, error) {
		if strings.HasPrefix(strings.TrimSpace(query), "UPDATE") {
			return fakeResult(0), nil
		}
		return fakeResult(1), nil
	}
	ok, err = claimInject(context.Background(), fe, "s", "p", "hint")
	if !ok || err != nil || len(fe.calls) != 2 {
		t.Fatalf("insert path: ok=%v err=%v calls=%d", ok, err, len(fe.calls))
	}

	// Budget exhausted -> INSERT hits ER_DUP_ENTRY.
	fe = &fakeExecer{handler: func(query string) (sql.Result, error) {
		if strings.HasPrefix(strings.TrimSpace(query), "UPDATE") {
			return fakeResult(0), nil
		}
		return nil, dupErr()
	}}
	ok, err = claimInject(context.Background(), fe, "s", "p", "hint")
	if ok || err != nil {
		t.Fatalf("exhausted: ok=%v err=%v, want false,nil", ok, err)
	}
}
