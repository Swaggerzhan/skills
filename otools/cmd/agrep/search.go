package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	searchLimit = 100
	maxLineLen  = 2000
	maxRgStdout = 1 << 20 // kill rg once stdout passes 1MB
)

type grepMatch struct {
	path    string
	modTime int64
	lineNum int
	text    string
}

type searchResult struct {
	files     int
	lines     int
	truncated bool
	output    string
}

// statMtime returns a file's mtime in ms. Variable for tests.
var statMtime = func(path string) (int64, error) {
	st, err := os.Stat(path)
	if err != nil {
		return 0, err
	}
	return st.ModTime().UnixMilli(), nil
}

// search runs rg under root and formats the grouped result. The returned
// error is the message handed to the shell's failure path.
func search(ctx context.Context, pattern, include, root string, filterOn bool) (searchResult, error) {
	args := []string{"--no-config", "--json", "--hidden", "--no-messages", "--no-ignore-parent"}
	args = append(args, "--glob="+include)
	if filterOn {
		for _, p := range genFilePatterns {
			args = append(args, "--glob=!"+p)
		}
	}
	args = append(args, "--glob=!**/.git/**", "--", pattern, ".")

	res, err := runCmd(ctx, root, maxRgStdout, "rg", args...)
	if err != nil {
		return searchResult{}, fmt.Errorf("failed to run rg: %v", err)
	}
	stderr := strings.TrimSpace(string(res.stderr))
	if !res.killed {
		if stderr != "" && res.code != 0 {
			return searchResult{}, fmt.Errorf("ripgrep error: %s", stderr)
		}
		if res.code == 2 {
			if stderr == "" {
				stderr = "Search failed"
			}
			return searchResult{}, fmt.Errorf("ripgrep error: %s", stderr)
		}
	}

	var matches []grepMatch
	for _, line := range strings.Split(strings.TrimSpace(string(res.stdout)), "\n") {
		if line == "" {
			continue
		}
		m, ok := parseRgLine(line, root)
		if !ok {
			continue
		}
		matches = append(matches, m)
		if len(matches) >= searchLimit {
			break
		}
	}

	if len(matches) == 0 {
		return searchResult{lines: 0, files: 0, truncated: false, output: "No files found"}, nil
	}

	files := map[string]bool{}
	for _, m := range matches {
		files[m.path] = true
	}

	sort.SliceStable(matches, func(i, j int) bool { return matches[i].modTime > matches[j].modTime })

	var b strings.Builder
	fmt.Fprintf(&b, "Found %d matches", len(matches))
	currentFile := ""
	num := 0
	for _, m := range matches {
		if currentFile != m.path {
			if currentFile != "" {
				b.WriteByte('\n')
			}
			b.WriteByte('\n')
			b.WriteString(m.path)
			b.WriteByte(':')
			currentFile = m.path
		}
		num++
		if num < searchLimit {
			fmt.Fprintf(&b, "\n  Line %d: %s", m.lineNum, m.text)
		}
	}
	if len(matches) >= searchLimit {
		b.WriteString("\n\n(Results truncated. Consider using a more specific path or pattern.)")
	}
	return searchResult{files: len(files), lines: len(matches), truncated: len(matches) >= searchLimit, output: b.String()}, nil
}

// parseRgLine decodes one rg --json line; non-match events, undecodable
// lines, and files that fail to stat are skipped.
func parseRgLine(line, root string) (grepMatch, bool) {
	var ev struct {
		Type string `json:"type"`
		Data struct {
			Path struct {
				Text string `json:"text"`
			} `json:"path"`
			LineNumber int `json:"line_number"`
			Lines      struct {
				Text string `json:"text"`
			} `json:"lines"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(line), &ev); err != nil || ev.Type != "match" || ev.Data.Path.Text == "" {
		return grepMatch{}, false
	}
	mt, err := statMtime(filepath.Join(root, ev.Data.Path.Text))
	if err != nil {
		return grepMatch{}, false
	}
	return grepMatch{
		path:    ev.Data.Path.Text,
		modTime: mt,
		lineNum: ev.Data.LineNumber,
		text:    truncateLine(strings.TrimSpace(ev.Data.Lines.Text), maxLineLen),
	}, true
}

// truncateLine caps a match line at maxLength chars; when a newline exists
// past 70% of the cut point the cut happens there instead.
func truncateLine(content string, maxLength int) string {
	if len(content) <= maxLength {
		return content
	}
	truncated := content[:maxLength]
	if idx := strings.LastIndex(truncated, "\n"); idx > int(float64(maxLength)*0.7) {
		return truncated[:idx] + "..."
	}
	return truncated + "..."
}
