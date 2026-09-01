// Custom tool `dep_search`: read-only entry point to the codebase-memory
// knowledge graph. It pipes a JSON argument object on stdin to the
// codebase-memory-mcp CLI one-shot mode (`cli <action>`), so agents never
// touch the raw MCP surface: the `dep-search_*` MCP tools stay denied and
// this wrapper is the only allowed path. The tool id is "dep_search" (the
// file name), which is also the permission key.
//
// Binary must match the MCP server entry in opencode.jsonc: same binary,
// same cache root, or the CLI is rejected by the admission barrier.

import { execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)

const BIN = "/tools/bin/codebase-memory-mcp"
const MAX_OUT = 48 * 1024

// Whitelisted args per action; anything else is dropped before reaching
// the CLI.
const ACTIONS: Record<string, string[]> = {
  list_projects: ["include_details", "limit", "offset"],
  search_graph: [
    "project", "query", "name_pattern", "label", "qn_pattern",
    "file_pattern", "limit", "offset", "format", "detail",
  ],
  search_code: [
    "project", "pattern", "file_pattern", "path_filter", "mode",
    "context", "regex", "limit",
  ],
  get_code_snippet: ["project", "qualified_name", "include_neighbors"],
  trace_path: [
    "project", "function_name", "direction", "depth", "mode",
    "limit", "cursor", "include_tests", "edge_types",
  ],
  check_index_coverage: [
    "project", "paths", "scopes", "scope_limit", "scope_offset",
  ],
}

const REQUIRED: Record<string, string[]> = {
  search_graph: ["project"],
  search_code: ["project", "pattern"],
  get_code_snippet: ["project", "qualified_name"],
  trace_path: ["project", "function_name"],
  check_index_coverage: ["project"],
}

const DESCRIPTION = [
  "Query the codebase-memory knowledge graph (read-only). Actions:",
  "- list_projects: list indexed projects; use each entry's name as the project arg elsewhere.",
  "- search_graph: find symbol definitions. Give name_pattern (regex) or query (full-text).",
  "  Rows show a qn prefix group; full qualified_name = group prefix + \".\" + row name.",
  "- search_code: graph-augmented grep over indexed files only (unindexed files are invisible).",
  "- get_code_snippet: read a symbol's exact source; get qualified_name from search_graph first.",
  "- trace_path: callers of a function (direction=\\\"inbound\\\") or its callees (\\\"outbound\\\").",
  "  If the result has a 'next' cursor, pass it back as cursor to page.",
  "- check_index_coverage: verify index completeness for paths/scopes (parse_partial, skipped).",
  "Discipline: graph results are best-effort. Before concluding 'no callers' / 'nothing found',",
  "run check_index_coverage on the involved paths; for parse_partial or skipped files, fall back",
  "to grep on the source.",
].join("\n")

export default {
  description: DESCRIPTION,
  args: {
    action: {
      type: "string",
      description: `One of: ${Object.keys(ACTIONS).join(", ")}`,
    },
    project: { type: "string", description: "Project name from list_projects" },
    query: { type: "string", description: "search_graph: BM25 full-text query" },
    name_pattern: { type: "string", description: "search_graph: regex on symbol name" },
    label: { type: "string", description: "search_graph: e.g. Function, Method, Class" },
    qn_pattern: { type: "string", description: "search_graph: regex on qualified name" },
    file_pattern: { type: "string", description: "File glob filter" },
    limit: { type: "number", description: "Max rows" },
    offset: { type: "number", description: "Skip first N rows (search_graph paging)" },
    format: { type: "string", description: "search_graph: tree (default) or json" },
    detail: { type: "string", description: "search_graph: ids or default" },
    pattern: { type: "string", description: "search_code: text or regex to grep" },
    path_filter: { type: "string", description: "search_code: regex on result file paths" },
    mode: { type: "string", description: "search_code: compact/full/files; trace_path: calls/data_flow/cross_service" },
    context: { type: "number", description: "search_code: context lines per match" },
    regex: { type: "boolean", description: "search_code: treat pattern as regex" },
    qualified_name: { type: "string", description: "get_code_snippet: full qn from search_graph" },
    include_neighbors: { type: "boolean", description: "get_code_snippet: also show related symbols" },
    function_name: { type: "string", description: "trace_path: function or method name" },
    direction: { type: "string", description: "trace_path: inbound (callers) / outbound (callees) / both" },
    depth: { type: "number", description: "trace_path: max hops (default 3)" },
    cursor: { type: "string", description: "trace_path: pass back the 'next' cursor to page" },
    include_tests: { type: "boolean", description: "trace_path: include test files (default false)" },
    edge_types: { type: "array", items: { type: "string" }, description: "trace_path: restrict edge types" },
    include_details: { type: "boolean", description: "list_projects: add branch/node/edge counts" },
    paths: { type: "array", items: { type: "string" }, description: "check_index_coverage: repo-relative files" },
    scopes: { type: "array", items: { type: "string" }, description: "check_index_coverage: repo-relative dir prefixes" },
    scope_limit: { type: "number", description: "check_index_coverage: rows per scope" },
    scope_offset: { type: "number", description: "check_index_coverage: scope paging" },
  },

  async execute(input: Record<string, unknown>, _ctx: { directory: string }) {
    const action = String(input.action ?? "")
    const allowed = ACTIONS[action]
    if (!allowed) {
      return `unknown action: ${action || "(missing)"} (allowed: ${Object.keys(ACTIONS).join(", ")})`
    }
    const missing = (REQUIRED[action] ?? []).filter((k) => input[k] === undefined || input[k] === "")
    if (missing.length > 0) {
      return `action ${action} requires: ${missing.join(", ")}`
    }
    if (action === "check_index_coverage" && !input.paths && !input.scopes) {
      return "check_index_coverage requires at least one of: paths, scopes"
    }

    const payload: Record<string, unknown> = {}
    for (const key of allowed) {
      if (input[key] !== undefined) payload[key] = input[key]
    }

    try {
      const p = exec(BIN, ["cli", action], { timeout: 60_000, maxBuffer: MAX_OUT })
      if (Object.keys(payload).length > 0) {
        p.child.stdin?.end(JSON.stringify(payload))
      }
      const out = await p
      const text = (out.stdout ?? "").trim()
      if (text.length > MAX_OUT) {
        return text.slice(0, MAX_OUT) + `\n... (truncated at ${MAX_OUT} bytes; narrow the query or page with limit/offset/cursor)`
      }
      return text || "(no output)"
    } catch (err) {
      const e = err as { stdout?: string; stderr?: string; code?: unknown }
      return [
        (e.stdout ?? "").trim(),
        (e.stderr ?? "").trim(),
        `dep_search ${action} failed (exit code ${String(e.code ?? "unknown")})`,
      ]
        .filter(Boolean)
        .join("\n")
    }
  },
}
