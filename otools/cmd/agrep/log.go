package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// logWarn appends one line to the regular opencode log. Logging never breaks
// the tool: every failure is swallowed, mirroring the TS sidecar semantics.
func logWarn(format string, args ...any) {
	defer func() { _ = recover() }()
	base := os.Getenv("XDG_DATA_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return
		}
		base = filepath.Join(home, ".local", "share")
	}
	file := filepath.Join(base, "opencode", "log", "opencode.log")
	msg, _ := json.Marshal(fmt.Sprintf(format, args...))
	line := fmt.Sprintf("timestamp=%s level=WARN service=agrep message=%s\n", time.Now().Format(time.RFC3339Nano), msg)
	f, err := os.OpenFile(file, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.WriteString(line)
}
