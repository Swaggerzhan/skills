package main

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"time"
)

// genFilePatterns are appended as rg exclusion globs (same level as the
// hardcoded !**/.git/**) unless proto_gen_file_filter is explicitly false.
// Double-suffix
// patterns matter: "*.h" includes would otherwise pull in "*.pb.h".
var genFilePatterns = []string{
	// C/C++
	"*.pb.h", "*.pb.cc", "*.grpc.pb.h", "*.grpc.pb.cc", "*.pb.validate.h", "*.pb.validate.cc",
	// Python
	"*_pb2.py", "*_pb2.pyi", "*_pb2_grpc.py",
	// Rust (convention; prost itself has no filename marker)
	"*.pb.rs",
	// Go
	"*.pb.go", "*_grpc.pb.go", "*.pb.gw.go", "*.pb.validate.go",
	// JS/TS
	"*_pb.js", "*_pb.d.ts", "*_grpc_pb.js", "*_grpc_pb.d.ts",
}

const filterProbeTimeout = 5 * time.Second

// activeGenPatterns returns the exclusion patterns relevant to the include's
// suffixes (empty for extension-less globs like "Makefile").
func activeGenPatterns(include string) []string {
	exts := map[string]bool{}
	for _, e := range extractExts(include) {
		exts[e] = true
	}
	if len(exts) == 0 {
		return nil
	}
	var out []string
	for _, p := range genFilePatterns {
		if exts[p[strings.LastIndex(p, ".")+1:]] {
			out = append(out, p)
		}
	}
	return out
}

// probeFilteredFile reports the first generated file matching patterns under
// root, or "" when none exist or the probe fails (probe failure adds no hint).
func probeFilteredFile(ctx context.Context, root string, patterns []string) string {
	if len(patterns) == 0 {
		return ""
	}
	ctx, cancel := context.WithTimeout(ctx, filterProbeTimeout)
	defer cancel()
	args := []string{"--no-config", "--hidden", "--no-messages", "--no-ignore-parent"}
	for _, p := range patterns {
		args = append(args, "--glob="+p)
	}
	args = append(args, "--files")
	res, err := runCmd(ctx, root, 64*1024, "rg", args...)
	if err != nil || ctx.Err() != nil {
		return ""
	}
	if !res.killed && res.code != 0 {
		return ""
	}
	first, _, _ := strings.Cut(string(res.stdout), "\n")
	return strings.TrimSpace(first)
}

var braceRe = regexp.MustCompile(`\{([^{}]*)\}`)
var extRe = regexp.MustCompile(`\.([A-Za-z0-9]+)$`)

// extractExts expands one level of brace alternation ("*.{h,cc}" -> "*.h",
// "*.cc") and takes the trailing .ext of each branch's basename.
func extractExts(glob string) []string {
	var branches []string
	if m := braceRe.FindStringSubmatchIndex(glob); m != nil {
		for _, alt := range strings.Split(glob[m[2]:m[3]], ",") {
			branches = append(branches, glob[:m[0]]+alt+glob[m[1]:])
		}
	} else {
		branches = []string{glob}
	}
	var exts []string
	for _, b := range branches {
		base := b[strings.LastIndex(b, "/")+1:]
		if m := extRe.FindStringSubmatch(base); m != nil {
			exts = append(exts, strings.ToLower(m[1]))
		}
	}
	return exts
}

// protoGenHint is the generated-code-filter notice line.
func protoGenHint(probed string) string {
	return fmt.Sprintf(`[proto_gen_filter]: generated files like "%s" filtered out; do not read generated code — the .proto is enough.`, probed)
}
