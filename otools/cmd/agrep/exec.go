package main

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
	"sync"
)

// cmdResult is the outcome of one external command run.
type cmdResult struct {
	stdout []byte
	stderr []byte
	code   int  // process exit code; -1 when the process never exited normally
	killed bool // killed because stdout exceeded the cap
}

// runCmd executes name with args in dir, capturing stdout (capped at
// maxStdout; the process is killed once the cap is exceeded) and stderr
// (capped at 64KB). It is a variable so tests can substitute a fake without
// touching rg / codebase-memory-mcp / make.
var runCmd = func(ctx context.Context, dir string, maxStdout int, name string, args ...string) (cmdResult, error) {
	inner, cancel := context.WithCancel(ctx)
	defer cancel()

	cmd := exec.CommandContext(inner, name, args...)
	if dir != "" {
		cmd.Dir = dir
	}
	out := &cappedWriter{limit: maxStdout, onExceed: cancel}
	cmd.Stdout = out
	errBuf := &cappedWriter{limit: 64 * 1024}
	cmd.Stderr = errBuf

	var res cmdResult
	if err := cmd.Start(); err != nil {
		return res, err
	}
	err := cmd.Wait()
	res.stdout, res.stderr = out.buf.Bytes(), errBuf.buf.Bytes()
	res.killed = out.exceeded
	res.code = 0
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			res.code = exitErr.ExitCode()
		} else if !errors.Is(err, context.Canceled) {
			return res, err
		} else {
			res.code = -1
		}
	}
	return res, nil
}

// cappedWriter buffers up to limit bytes and fires onExceed once the limit is
// exceeded (used to kill the producing process).
type cappedWriter struct {
	mu       sync.Mutex
	buf      bytes.Buffer
	limit    int
	exceeded bool
	onExceed func()
}

func (w *cappedWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.limit > 0 && w.buf.Len()+len(p) > w.limit {
		remain := w.limit - w.buf.Len()
		if remain > 0 {
			w.buf.Write(p[:remain])
		}
		if !w.exceeded {
			w.exceeded = true
			if w.onExceed != nil {
				w.onExceed()
			}
		}
		return len(p), nil
	}
	w.buf.Write(p)
	return len(p), nil
}
