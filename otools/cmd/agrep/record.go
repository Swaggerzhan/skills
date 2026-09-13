package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	mysql "github.com/go-sql-driver/mysql"
)

// sqlExecer is the subset of *sql.DB the recorder needs; tests substitute a
// fake so no real MySQL is involved.
type sqlExecer interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

const ddlRecords = `CREATE TABLE IF NOT EXISTS agrep_records (
  session_id   VARCHAR(64)     NOT NULL,
  message_id   VARCHAR(64)     NOT NULL,
  turn_id      INT UNSIGNED    NOT NULL,
  created_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  agent        VARCHAR(64)     NOT NULL,
  pattern      TEXT            NULL,
  path         VARCHAR(1024)   NOT NULL,
  include      VARCHAR(255)    NULL,
  intent       TEXT            NOT NULL,
  matched_files  INT             NULL,
  matched_lines  INT             NULL,
  truncated    TINYINT(1)      NULL,
  output_text  MEDIUMTEXT      NULL,
  error        TEXT            NULL,
  PRIMARY KEY (session_id, message_id, turn_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`

const ddlInject = `CREATE TABLE IF NOT EXISTS agrep_inject_records (
  session_id     VARCHAR(64)  NOT NULL,
  project_name   VARCHAR(255) NOT NULL,
  inject_count   INT UNSIGNED NOT NULL DEFAULT 0,
  inject_content TEXT         NULL,
  PRIMARY KEY (session_id, project_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`

const dsInjectLimit = 3

// openDB connects, verifies reachability, and ensures both tables exist.
func openDB(ctx context.Context, cfg *mysqlConfig) (*sql.DB, error) {
	dsn := fmt.Sprintf("%s:%s@tcp(%s)/%s?charset=utf8mb4&timeout=3s",
		cfg.Username, cfg.Password, cfg.hostPort(), cfg.Database)
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, err
	}
	pingCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		db.Close()
		return nil, err
	}
	if err := ensureSchema(ctx, db); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

func ensureSchema(ctx context.Context, e sqlExecer) error {
	if _, err := e.ExecContext(ctx, ddlRecords); err != nil {
		return err
	}
	_, err := e.ExecContext(ctx, ddlInject)
	return err
}

// recordRow is one agrep_records row. Nullable columns are pointers.
type recordRow struct {
	SessionID    string
	MessageID    string
	Agent        string
	Pattern      *string
	Path         string
	Include      *string
	Intent       string
	MatchedFiles *int
	MatchedLines *int
	Truncated    *int
	Output       *string
	Error        *string
}

const insertRecordSQL = `INSERT INTO agrep_records
  (session_id, message_id, turn_id, agent, pattern, path, include, intent, matched_files, matched_lines, truncated, output_text, error)
SELECT ?, ?, COALESCE(MAX(turn_id), 0) + 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
FROM agrep_records WHERE session_id = ? AND message_id = ?`

// insertRecord inserts one row with a per-(session,message) monotonically
// increasing turn_id (InnoDB has no grouped auto-increment, so MAX+1 via
// INSERT ... SELECT; ER_DUP_ENTRY from a concurrent insert triggers retry).
func insertRecord(ctx context.Context, e sqlExecer, row recordRow) error {
	var lastErr error
	for attempt := 0; attempt < 5; attempt++ {
		_, err := e.ExecContext(ctx, insertRecordSQL,
			row.SessionID, row.MessageID,
			row.Agent, row.Pattern, row.Path, row.Include, row.Intent,
			row.MatchedFiles, row.MatchedLines, row.Truncated, row.Output, row.Error,
			row.SessionID, row.MessageID,
		)
		if err == nil {
			return nil
		}
		if !isDupEntry(err) {
			return err
		}
		lastErr = err
	}
	return lastErr
}

// claimInject atomically takes one injection-budget slot (conditional UPDATE
// holds a row lock; ER_DUP_ENTRY on the fallback INSERT means the row exists
// at the limit).
func claimInject(ctx context.Context, e sqlExecer, sessionID, project, content string) (bool, error) {
	res, err := e.ExecContext(ctx,
		`UPDATE agrep_inject_records SET inject_count = inject_count + 1, inject_content = ?
		 WHERE session_id = ? AND project_name = ? AND inject_count < ?`,
		content, sessionID, project, dsInjectLimit)
	if err != nil {
		return false, err
	}
	if n, _ := res.RowsAffected(); n > 0 {
		return true, nil
	}
	_, err = e.ExecContext(ctx,
		`INSERT INTO agrep_inject_records (session_id, project_name, inject_count, inject_content) VALUES (?, ?, 1, ?)`,
		sessionID, project, content)
	if err != nil {
		if isDupEntry(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func isDupEntry(err error) bool {
	var mErr *mysql.MySQLError
	return errors.As(err, &mErr) && mErr.Number == 1062
}
