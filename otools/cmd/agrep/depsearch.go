package main

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// codeExts: an include restricting the search to any of these may cover an
// indexed codebase.
var codeExts = map[string]bool{
	"c": true, "h": true, "cc": true, "cpp": true, "cxx": true, "hh": true, "hpp": true, "hxx": true,
	"cu": true, "cuh": true, "m": true, "mm": true, "go": true, "rs": true, "zig": true, "nim": true,
	"d": true, "v": true, "sv": true,
	"js": true, "jsx": true, "mjs": true, "cjs": true, "ts": true, "tsx": true, "mts": true, "cts": true,
	"vue": true, "svelte": true, "py": true, "rb": true, "php": true, "lua": true, "pl": true, "pm": true,
	"r": true, "jl": true, "ex": true, "exs": true, "erl": true, "hrl": true,
	"java": true, "kt": true, "kts": true, "scala": true, "groovy": true, "cs": true, "fs": true,
	"vb": true, "swift": true, "dart": true, "hs": true, "ml": true, "mli": true, "clj": true,
	"cljs": true, "elm": true, "sh": true, "bash": true, "zsh": true, "sql": true, "proto": true,
}

const dsCliTimeout = 10 * time.Second

type dsProject struct {
	name string
	root string
}

// dsProjects execs the cbm CLI and parses the payload JSON:
// {"projects":[{"name","root_path"},...], ...}.
func dsProjects(ctx context.Context) ([]dsProject, error) {
	ctx, cancel := context.WithTimeout(ctx, dsCliTimeout)
	defer cancel()
	res, err := runCmd(ctx, "", 4<<20, "codebase-memory-mcp", "cli", "list_projects", "--limit", "100")
	if err != nil {
		return nil, err
	}
	if res.code != 0 {
		return nil, fmt.Errorf("codebase-memory-mcp cli exited %d: %s", res.code, strings.TrimSpace(string(res.stderr)))
	}
	var payload struct {
		Projects []struct {
			Name     string `json:"name"`
			RootPath string `json:"root_path"`
		} `json:"projects"`
	}
	if err := json.Unmarshal(res.stdout, &payload); err != nil {
		return nil, fmt.Errorf("cli output is not payload JSON: %w", err)
	}
	if payload.Projects == nil {
		return nil, fmt.Errorf("cli output has no projects array")
	}
	projects := make([]dsProject, 0, len(payload.Projects))
	for _, p := range payload.Projects {
		projects = append(projects, dsProject{name: p.Name, root: strings.TrimRight(p.RootPath, "/")})
	}
	return projects, nil
}

// matchProject picks the longest project root that contains searchRoot on a
// path boundary; nil when nothing contains it.
func matchProject(searchRoot string, projects []dsProject) *dsProject {
	root := strings.TrimRight(searchRoot, "/")
	var best *dsProject
	for i := range projects {
		p := &projects[i]
		if (root == p.root || strings.HasPrefix(root, p.root+"/")) && (best == nil || len(p.root) > len(best.root)) {
			best = p
		}
	}
	return best
}

// depSearchHint returns the hint line, or "" (not a code search / no
// matching project / budget exhausted / any failure — failures log WARN).
// db may be nil; the budget lives in MySQL, so recording-disabled means
// injection-disabled.
func depSearchHint(ctx context.Context, searchRoot, include, sessionID string, db sqlExecer) string {
	code := false
	for _, e := range extractExts(include) {
		if codeExts[e] {
			code = true
			break
		}
	}
	if !code {
		return ""
	}
	projects, err := dsProjects(ctx)
	if err != nil {
		logWarn("dep_search hint failed: %v", err)
		return ""
	}
	best := matchProject(searchRoot, projects)
	if best == nil {
		return ""
	}
	if db == nil {
		return ""
	}
	hint := fmt.Sprintf(`[dep_search]: this code is indexed. For faster structural code search, use the dep_search_* tools with project "%s".`, best.name)
	allowed, err := claimInject(ctx, db, sessionID, best.name, hint)
	if err != nil {
		logWarn("dep_search hint failed: %v", err)
		return ""
	}
	if !allowed {
		return ""
	}
	return hint
}
