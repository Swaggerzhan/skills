package main

import (
	"context"
	"database/sql"
	"testing"
)

func TestMatchProject(t *testing.T) {
	projects := []dsProject{
		{name: "mono", root: "/work/mono"},
		{name: "sub", root: "/work/mono/service"},
	}
	if got := matchProject("/work/mono/service/pkg", projects); got == nil || got.name != "sub" {
		t.Fatalf("longest prefix: %+v", got)
	}
	if got := matchProject("/work/mono/other", projects); got == nil || got.name != "mono" {
		t.Fatalf("parent prefix: %+v", got)
	}
	if got := matchProject("/work/monolithic", projects); got != nil {
		t.Fatalf("path boundary violated: %+v", got)
	}
	if got := matchProject("/elsewhere", projects); got != nil {
		t.Fatalf("unrelated: %+v", got)
	}
}

const cliPayload = `{"projects":[{"name":"brpc","root_path":"/code/brpc"},{"name":"x","root_path":"/code/x"}]}`

func TestDepSearchHint(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		if name != "codebase-memory-mcp" {
			t.Fatalf("unexpected cmd %q", name)
		}
		return cmdResult{stdout: []byte(cliPayload), code: 0}, nil
	})()
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(1), nil }}

	got := depSearchHint(context.Background(), "/code/brpc/src", "*.cc", "sess1", fe)
	want := `[dep_search]: this code is indexed. For faster structural code search, use the dep_search_* tools with project "brpc".`
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
	// Budget content recorded in the inject table.
	if fe.calls[0] == "" {
		t.Fatal("budget not claimed")
	}
}

func TestDepSearchHintNonCodeInclude(t *testing.T) {
	called := false
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		called = true
		return cmdResult{}, nil
	})()
	if got := depSearchHint(context.Background(), "/code/brpc", "*.md", "s", nil); got != "" {
		t.Fatalf("got %q", got)
	}
	if called {
		t.Fatal("CLI must not run for non-code include")
	}
}

func TestDepSearchHintBudgetExhausted(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{stdout: []byte(cliPayload), code: 0}, nil
	})()
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(0), dupErr() }}
	if got := depSearchHint(context.Background(), "/code/brpc", "*.cc", "sess1", fe); got != "" {
		t.Fatalf("budget exhausted must yield no hint, got %q", got)
	}
}

func TestDepSearchHintNoDB(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{stdout: []byte(cliPayload), code: 0}, nil
	})()
	if got := depSearchHint(context.Background(), "/code/brpc", "*.cc", "sess1", nil); got != "" {
		t.Fatalf("recording disabled => injection disabled, got %q", got)
	}
}

func TestDepSearchHintCliFailure(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{stderr: []byte("boom"), code: 1}, nil
	})()
	fe := &fakeExecer{handler: func(query string) (sql.Result, error) { return fakeResult(1), nil }}
	if got := depSearchHint(context.Background(), "/code/brpc", "*.cc", "sess1", fe); got != "" {
		t.Fatalf("CLI failure must yield no hint, got %q", got)
	}
}
