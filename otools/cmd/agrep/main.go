package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
)

type cliArgs struct {
	pattern, include, intent, path string
	sessionID, messageID, agent    string
}

// The shell passes its flags as --name=value. Exit 0 → stdout is the
// result; exit 1 → stdout is the error message for the shell to throw.
// Flag-parse errors keep the flag package default (usage to stderr, exit 2).
func main() {
	var a cliArgs
	flag.StringVar(&a.pattern, "pattern", "", "rg search pattern")
	flag.StringVar(&a.include, "include", "", "file glob")
	flag.StringVar(&a.intent, "intent", "", "search intent")
	flag.StringVar(&a.path, "path", "", "search root, absolute")
	flag.StringVar(&a.sessionID, "session-id", "", "session id")
	flag.StringVar(&a.messageID, "message-id", "", "message id")
	flag.StringVar(&a.agent, "agent", "", "calling agent")
	flag.Parse()

	ctx := context.Background()

	cfg, cfgErr := loadConfig(defaultConfigPath())
	if cfgErr != nil {
		logWarn("config disabled: %v", cfgErr)
	}
	filterOn := cfg.filterEnabled()

	var db *sqlDB
	if cfg != nil && cfg.MySQL != nil {
		if d, err := openDB(ctx, cfg.MySQL); err != nil {
			logWarn("recording disabled: MySQL init failed: %v", err)
		} else {
			db = &sqlDB{db: d}
			defer d.Close()
		}
	} else {
		logWarn("recording disabled: mysql config missing")
	}

	pattern := strings.TrimSpace(a.pattern)
	intent := strings.TrimSpace(a.intent)
	include := strings.TrimSpace(a.include)

	var problems []string
	if pattern == "" {
		problems = append(problems, "pattern is required")
	}
	if intent == "" {
		problems = append(problems, "intent is required (a short phrase stating why you need this search)")
	}
	if include == "" {
		problems = append(problems, `include is required (a file glob such as "*.cc" or a file name like "Makefile")`)
	} else if include == "*" {
		problems = append(problems, `include "*" is not allowed; use a specific glob such as "*.cc", "*.{h,hpp,cpp,cc}", or a file name like "Makefile"`)
	}
	if len(problems) > 0 {
		errMsg := strings.Join(problems, "; ")
		db.record(ctx, recordRow{
			SessionID: a.sessionID, MessageID: a.messageID,
			Agent:   a.agent,
			Pattern: strPtrOrNil(pattern), Path: a.path, Include: strPtrOrNil(include),
			Intent: intent, Error: &errMsg,
		})
		fmt.Println(errMsg)
		os.Exit(1)
	}

	res, err := search(ctx, pattern, include, a.path, filterOn)
	if err != nil {
		fmt.Println(err)
		os.Exit(1)
	}

	var hints []string
	if filterOn {
		if probed := probeFilteredFile(ctx, a.path, activeGenPatterns(include)); probed != "" {
			hints = append(hints, protoGenHint(probed))
		}
	}
	if hint := depSearchHint(ctx, a.path, include, a.sessionID, db.execer()); hint != "" {
		hints = append(hints, hint)
	}

	output := assemble(res.output, hints)
	db.record(ctx, recordRow{
		SessionID: a.sessionID, MessageID: a.messageID,
		Agent:   a.agent,
		Pattern: &pattern, Path: a.path, Include: &include, Intent: intent,
		MatchedFiles: &res.files, MatchedLines: &res.lines, Truncated: boolToIntPtr(res.truncated), Output: &output,
	})
	fmt.Print(output)
}

// sqlDB wraps *sql.DB so a nil *sqlDB can still serve the call sites (the
// sidecar pattern: every recording path is a no-op when disabled).
type sqlDB struct {
	db interface {
		sqlExecer
		Close() error
	}
}

func (s *sqlDB) execer() sqlExecer {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db
}

func (s *sqlDB) record(ctx context.Context, row recordRow) {
	if e := s.execer(); e != nil {
		if err := insertRecord(ctx, e, row); err != nil {
			logWarn("record failed: %v", err)
		}
	}
}

func strPtrOrNil(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func boolToIntPtr(b bool) *int {
	v := 0
	if b {
		v = 1
	}
	return &v
}
