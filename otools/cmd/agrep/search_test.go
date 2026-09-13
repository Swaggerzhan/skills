package main

import (
	"context"
	"fmt"
	"strings"
	"testing"
)

func rgJSONLine(file string, line int, text string) string {
	return fmt.Sprintf(`{"type":"match","data":{"path":{"text":%q},"lines":{"text":%q},"line_number":%d,"absolute_offset":0,"submatches":[]}}`, file, text+"\n", line)
}

func fakeStat(mtimes map[string]int64) func() {
	orig := statMtime
	statMtime = func(path string) (int64, error) {
		if v, ok := mtimes[path]; ok {
			return v, nil
		}
		return 0, fmt.Errorf("no such file: %s", path)
	}
	return func() { statMtime = orig }
}

func TestSearchFormatAndSort(t *testing.T) {
	defer fakeStat(map[string]int64{"/r/old.cc": 100, "/r/new.cc": 200})()
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		if dir != "/r" {
			t.Fatalf("rg cwd = %q, want /r", dir)
		}
		joined := strings.Join(args, " ")
		for _, want := range []string{"--glob=*.cc", "--glob=!*.pb.cc", "--glob=!**/.git/**", "--no-ignore-parent"} {
			if !strings.Contains(joined, want) {
				t.Fatalf("rg args missing %s: %v", want, args)
			}
		}
		out := rgJSONLine("old.cc", 1, "hit") + "\n" + rgJSONLine("new.cc", 2, "hit") + "\n"
		return cmdResult{stdout: []byte(out), code: 0}, nil
	})()

	res, err := search(context.Background(), "hit", "*.cc", "/r", true)
	if err != nil {
		t.Fatalf("search: %v", err)
	}
	want := "Found 2 matches\nnew.cc:\n  Line 2: hit\n\nold.cc:\n  Line 1: hit"
	if res.output != want {
		t.Fatalf("output:\n%q\nwant:\n%q", res.output, want)
	}
	if res.lines != 2 || res.files != 2 || res.truncated {
		t.Fatalf("lines=%d files=%d truncated=%v", res.lines, res.files, res.truncated)
	}
}

func TestSearchNoMatches(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{code: 1}, nil
	})()
	res, err := search(context.Background(), "x", "*.cc", "/r", true)
	if err != nil || res.output != "No files found" {
		t.Fatalf("got %q err=%v", res.output, err)
	}
}

func TestSearchRgError(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{stderr: []byte("regex parse error"), code: 2}, nil
	})()
	if _, err := search(context.Background(), "(", "*.cc", "/r", true); err == nil ||
		!strings.Contains(err.Error(), "regex parse error") {
		t.Fatalf("want ripgrep error, got %v", err)
	}
}

func TestSearchFilterOffSkipsGlobs(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		for _, a := range args {
			if strings.HasPrefix(a, "--glob=!*.pb") {
				t.Fatalf("proto_gen_file_filter=false must drop exclusion globs: %v", args)
			}
		}
		return cmdResult{code: 1}, nil
	})()
	if _, err := search(context.Background(), "x", "*.go", "/r", false); err != nil {
		t.Fatalf("search: %v", err)
	}
}

func TestSearchKilledKeepsPartial(t *testing.T) {
	defer fakeStat(map[string]int64{"/r/a.cc": 100})()
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{stdout: []byte(rgJSONLine("a.cc", 9, "hit") + "\n"), code: -1, killed: true}, nil
	})()
	res, err := search(context.Background(), "hit", "*.cc", "/r", true)
	if err != nil {
		t.Fatalf("killed rg must keep partial output: %v", err)
	}
	if !strings.Contains(res.output, "Line 9: hit") {
		t.Fatalf("partial output lost: %q", res.output)
	}
}

func TestTruncateLine(t *testing.T) {
	short := strings.Repeat("a", 100)
	if got := truncateLine(short, 2000); got != short {
		t.Fatal("short line modified")
	}
	long := strings.Repeat("a", 3000)
	if got := truncateLine(long, 2000); len(got) != 2003 || !strings.HasSuffix(got, "...") {
		t.Fatalf("len=%d", len(got))
	}
	withNL := strings.Repeat("a", 1500) + "\n" + strings.Repeat("b", 1000)
	got := truncateLine(withNL, 2000)
	if !strings.HasSuffix(got, "a...") || len(got) != 1503 {
		t.Fatalf("newline cut failed: len=%d suffix=%q", len(got), got[len(got)-10:])
	}
}

func TestSearchTruncationNote(t *testing.T) {
	defer fakeStat(map[string]int64{"/r/a.cc": 100})()
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		var b strings.Builder
		for i := 1; i <= 200; i++ {
			fmt.Fprintf(&b, "%s\n", rgJSONLine("a.cc", i, "hit"))
		}
		return cmdResult{stdout: []byte(b.String()), code: 0}, nil
	})()
	res, err := search(context.Background(), "hit", "*.cc", "/r", true)
	if err != nil {
		t.Fatalf("search: %v", err)
	}
	if res.lines != searchLimit || res.files != 1 || !res.truncated {
		t.Fatalf("lines=%d files=%d truncated=%v", res.lines, res.files, res.truncated)
	}
	if !strings.HasSuffix(res.output, "(Results truncated. Consider using a more specific path or pattern.)") {
		t.Fatalf("missing truncation note: %q", res.output[len(res.output)-80:])
	}
	if strings.Contains(res.output, "Line 100:") {
		t.Fatal("the 100th match line must not be printed (TS parity)")
	}
	if !strings.HasPrefix(res.output, "Found 100 matches") {
		t.Fatalf("header: %q", res.output)
	}
}
