import { spawn } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { StringDecoder } from "node:string_decoder"
import { tool } from "@opencode-ai/plugin"
// mysql2 is imported lazily inside db(): tool files deploy via git/symlink while
// node_modules does not, so a top-level import of an uninstalled package would
// crash the whole tool registry at load time and break every session. A lazy
// import confines the failure to the recording path, which degrades silently.
import type mysql from "mysql2/promise"

// Clone of the built-in grep tool, plus a required `intent` parameter.
// Every call (inputs + full output) is recorded to a global MySQL table.
// Recording is a sidecar: any MySQL problem (missing env, unreachable server,
// failed insert) disables/skips recording silently and only logs a WARN line
// to the opencode log — the search itself must never fail because of it.

const DESCRIPTION = `- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- The \`include\` parameter is REQUIRED: a glob that restricts which files are searched (e.g. "*.cc", "*.{h,hpp,cpp,cc}", or a file name like "Makefile"); a bare "*" is not allowed
- Returns file paths and line numbers with matching lines
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with \`rg\` (ripgrep) directly
- When you are doing an open-ended search that may require multiple rounds of globbing and grepping, use the Task tool instead
- The \`intent\` parameter is REQUIRED: a short phrase in English (just a few words) stating why you need this search (e.g. "get references", "find definition", "understand implementation", "audit usage", "locate error source"). It does not change the search behavior.`

const LIMIT = 100

export default tool({
  description: DESCRIPTION,
  args: {
    intent: tool.schema
      .string()
      .describe(
        'Why you need this search (REQUIRED: short phrase in English, just a few words, such as "get references", "find definition", "understand implementation", "audit usage", "locate error source")',
      ),
    pattern: tool.schema.string().describe("The regex pattern to search for in file contents"),
    path: tool.schema
      .string()
      .describe("The directory to search in. Defaults to the current working directory.")
      .optional(),
    include: tool.schema
      .string()
      .describe('The glob pattern to match files against (REQUIRED: e.g. "*.cc", "*.{h,hpp,cpp,cc}", or a file name like "Makefile"; a bare "*" is not allowed)'),
  },
  async execute(args, context) {
    const pattern = args.pattern?.trim()
    const intentText = args.intent?.trim()
    const include = args.include?.trim()
    const includeProblem = !include
      ? 'include is required (a file glob such as "*.cc" or a file name like "Makefile")'
      : include === "*"
        ? 'include "*" is not allowed; use a specific glob such as "*.cc", "*.{h,hpp,cpp,cc}", or a file name like "Makefile"'
        : null
    const problems = [
      pattern ? null : "pattern is required",
      intentText ? null : "intent is required (a short phrase stating why you need this search)",
      includeProblem,
    ].filter(Boolean) as string[]
    if (problems.length) {
      const error = problems.join("; ")
      await record({
        sessionId: context.sessionID,
        agent: context.agent,
        directory: context.directory,
        pattern: pattern ?? null,
        path: resolveSearchRoot(args.path, context.directory),
        include: include ?? null,
        intent: intentText ?? "",
        matches: null,
        truncated: null,
        output: null,
        error,
      })
      throw new Error(error)
    }

    const result = await search(pattern!, include!, resolveSearchRoot(args.path, context.directory))
    const reminders: string[] = []
    if (!filterDisabled()) {
      const filtered = await probeFilteredFile(result.searchRoot, activeGenPatterns(include!))
      if (filtered) {
        reminders.push(
          `[proto_gen_filter]: generated files like "${filtered}" are filtered out; ` +
            `you should not read generated code — the .proto definition is enough.`,
        )
      }
    }
    const dsHint = await depSearchHint(result.searchRoot, include!, context.sessionID)
    if (dsHint) reminders.push(dsHint)
    const output = result.output + (reminders.length ? `\n\nReminder:\n${reminders.join("\n")}\n` : "")
    await record({
      sessionId: context.sessionID,
      agent: context.agent,
      directory: context.directory,
      pattern: pattern!,
      path: result.searchRoot,
      include: include!,
      intent: intentText!,
      matches: result.matches,
      truncated: result.truncated ? 1 : 0,
      output,
      error: null,
    })
    return {
      title: pattern!,
      metadata: { matches: result.matches, truncated: result.truncated },
      output,
    }
  },
})

// ---------- record store (MySQL) ----------

type Config = { host: string; port: number; user: string; password: string; database: string }

const REQUIRED_ENV = [
  "OPENCODE_AGREP_MYSQL_ENDPOINT",
  "OPENCODE_AGREP_MYSQL_USERNAME",
  "OPENCODE_AGREP_MYSQL_PASSWORD",
  "OPENCODE_AGREP_MYSQL_DATABASE_NAME",
] as const

// Table names are fixed: they auto-create (CREATE TABLE IF NOT EXISTS), so a
// configurable name buys nothing and a missing/wrong value used to silently
// disable recording when it was still required env.
const MAIN_TABLE = "agrep_records"
const INJECT_TABLE = "agrep_inject_records"

type EnvMap = Partial<Record<(typeof REQUIRED_ENV)[number], string>>

function fromEnv(): EnvMap {
  const env: EnvMap = {}
  for (const name of REQUIRED_ENV) {
    const value = process.env[name]?.trim()
    if (value) env[name] = value
  }
  return env
}

// WARN line appended to the regular opencode log file; logging itself never throws.
function logWarn(message: string) {
  try {
    const base = process.env.XDG_DATA_HOME ?? path.join(os.homedir(), ".local", "share")
    const file = path.join(base, "opencode", "log", "opencode.log")
    fs.appendFileSync(file, `timestamp=${new Date().toISOString()} level=WARN service=agrep message=${JSON.stringify(message)}\n`)
  } catch {
    // never break the tool because of logging
  }
}

let cached: Config | null | undefined

function getConfig(): Config | null {
  if (cached !== undefined) return cached
  const env = fromEnv()
  const missing = REQUIRED_ENV.filter((name) => !env[name])
  if (missing.length) {
    logWarn(`recording disabled: missing env: ${missing.join(", ")}`)
    cached = null
    return cached
  }
  const endpoint = env.OPENCODE_AGREP_MYSQL_ENDPOINT!
  const idx = endpoint.lastIndexOf(":")
  cached = {
    host: idx > 0 ? endpoint.slice(0, idx) : endpoint,
    port: idx > 0 ? Number(endpoint.slice(idx + 1)) : 3306,
    user: env.OPENCODE_AGREP_MYSQL_USERNAME!,
    password: env.OPENCODE_AGREP_MYSQL_PASSWORD!,
    database: env.OPENCODE_AGREP_MYSQL_DATABASE_NAME!,
  }
  return cached
}

let ready: Promise<mysql.Pool | null> | undefined

function db() {
  if (!ready) {
    ready = (async () => {
      try {
        const cfg = getConfig()
        if (!cfg) return null
        const mysql = await import("mysql2/promise")
        const pool = mysql.default.createPool({
          host: cfg.host,
          port: cfg.port,
          user: cfg.user,
          password: cfg.password,
          database: cfg.database,
          charset: "utf8mb4",
          waitForConnections: true,
          connectionLimit: 4,
        })
        await pool.query(`CREATE TABLE IF NOT EXISTS \`${MAIN_TABLE}\` (
  session_id  VARCHAR(64)    NOT NULL,
  seq         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  created_at  DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  agent       VARCHAR(64)    NOT NULL,
  directory   VARCHAR(512)   NOT NULL,
  pattern     TEXT           NULL,
  path        VARCHAR(1024)  NOT NULL,
  include     VARCHAR(255)   NULL,
  intent      TEXT           NOT NULL,
  matches     INT            NULL,
  truncated   TINYINT(1)     NULL,
  output_text MEDIUMTEXT     NULL,
  error       TEXT           NULL,
  PRIMARY KEY (session_id, seq),
  KEY idx_seq (seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`)
        await pool.query(`CREATE TABLE IF NOT EXISTS \`${INJECT_TABLE}\` (
  session_id     VARCHAR(64)  NOT NULL,
  project_name   VARCHAR(255) NOT NULL,
  inject_count   INT UNSIGNED NOT NULL DEFAULT 0,
  inject_content TEXT         NULL,
  PRIMARY KEY (session_id, project_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`)
        return pool
      } catch (err) {
        logWarn(`recording disabled: MySQL init failed: ${String(err)}`)
        return null
      }
    })()
  }
  return ready
}

// Connect eagerly at module load; on failure recording stays disabled for the
// process lifetime (no retry) and the search path is unaffected.
void db()

async function record(row: {
  sessionId: string
  agent: string
  directory: string
  pattern: string | null
  path: string
  include: string | null
  intent: string
  matches: number | null
  truncated: 0 | 1 | null
  output: string | null
  error: string | null
}) {
  const pool = await db()
  if (!pool) return
  try {
    await pool.query(
      `INSERT INTO \`${MAIN_TABLE}\` (session_id, agent, directory, pattern, path, include, intent, matches, truncated, output_text, error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        row.sessionId,
        row.agent,
        row.directory,
        row.pattern,
        row.path,
        row.include,
        row.intent,
        row.matches,
        row.truncated,
        row.output,
        row.error,
      ],
    )
  } catch (err) {
    logWarn(`record failed: ${String(err)}`)
  }
}

// ---------- generated-protobuf-file filter (built-in, not LLM-controlled) ----------

// Double-suffix patterns: the real extension stays .h/.go/..., so an LLM-written
// "*.h" include would still pull in "*.pb.h" and blow up context. Unconditionally
// appended as rg exclusion globs (same level as the hardcoded !**/.git/**) unless
// OPENCODE_AGREP_NO_FILTER is set. Scoped to c/cpp/py/rust/go/js/ts generators.
export const GEN_FILE_PATTERNS = [
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
]

const FILTER_PROBE_TIMEOUT_MS = 5_000

export function filterDisabled(): boolean {
  const v = process.env.OPENCODE_AGREP_NO_FILTER?.trim().toLowerCase()
  return !!v && v !== "0" && v !== "false"
}

// The filter applies unconditionally, but the notice only fires when generated
// files relevant to this include actually exist under the search root.
export function activeGenPatterns(include: string): string[] {
  const exts = new Set(extractExts(include))
  if (!exts.size) return []
  return GEN_FILE_PATTERNS.filter((p) => exts.has(p.slice(p.lastIndexOf(".") + 1).toLowerCase()))
}

// Fast existence probe: rg --files is a filename-only scan, no content pass.
async function probeFilteredFile(searchRoot: string, patterns: string[]): Promise<string | null> {
  if (!patterns.length) return null
  return new Promise((resolve) => {
    const args = ["--no-config", "--hidden", "--no-messages"]
    for (const p of patterns) args.push(`--glob=${p}`)
    args.push("--files")
    const proc = spawn("rg", args, { cwd: searchRoot, stdio: ["ignore", "pipe", "ignore"] })
    let buf = ""
    let done = false
    const finish = (v: string | null) => {
      if (!done) {
        done = true
        clearTimeout(timer)
        proc.kill("SIGTERM")
        resolve(v)
      }
    }
    const timer = setTimeout(() => finish(null), FILTER_PROBE_TIMEOUT_MS)
    proc.stdout.on("data", (c: Buffer) => {
      buf += c.toString("utf8")
      const nl = buf.indexOf("\n")
      if (nl >= 0) finish(buf.slice(0, nl).trim() || null)
    })
    proc.on("error", () => finish(null))
    proc.on("close", () => finish(buf.trim().split("\n")[0]?.trim() || null))
  })
}

// ---------- dep_search hint injection ----------

// Common code-file suffixes. When `include` restricts the search to any of
// these, the searched tree may be an indexed codebase, so we check dep_search
// and tell the model (a few tokens appended to the output).
const CODE_EXTS = new Set([
  "c", "h", "cc", "cpp", "cxx", "hh", "hpp", "hxx", "cu", "cuh", "m", "mm",
  "go", "rs", "zig", "nim", "d", "v", "sv",
  "js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts", "vue", "svelte",
  "py", "rb", "php", "lua", "pl", "pm", "r", "jl", "ex", "exs", "erl", "hrl",
  "java", "kt", "kts", "scala", "groovy", "cs", "fs", "vb", "swift", "dart",
  "hs", "ml", "mli", "clj", "cljs", "elm", "sh", "bash", "zsh", "sql", "proto",
])

// Extract candidate suffixes from an rg glob: expands one level of brace
// alternation (`*.{h,cc}` -> `*.h`, `*.cc`) and takes the trailing `.ext` of
// each branch's basename. Returns [] for extension-less globs ("Makefile").
function extractExts(glob: string): string[] {
  const branches: string[] = []
  const brace = /\{([^{}]*)\}/.exec(glob)
  if (brace) {
    for (const alt of brace[1].split(",")) {
      branches.push(glob.slice(0, brace.index) + alt + glob.slice(brace.index + brace[0].length))
    }
  } else {
    branches.push(glob)
  }
  const exts: string[] = []
  for (const b of branches) {
    const base = b.slice(b.lastIndexOf("/") + 1)
    const m = /\.([A-Za-z0-9]+)$/.exec(base)
    if (m) exts.push(m[1].toLowerCase())
  }
  return exts
}

type DsProject = { name: string; root: string }

let dsCache: { at: number; projects: DsProject[] } | undefined
const DS_CACHE_TTL_MS = 60_000
const DS_CLI_TIMEOUT_MS = 10_000 // tolerate cold daemon start; cached afterwards

function runDsCli(): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn("codebase-memory-mcp", ["cli", "list_projects", "--limit", "100"], {
      stdio: ["ignore", "pipe", "pipe"],
    })
    let out = ""
    let err = ""
    const timer = setTimeout(() => {
      proc.kill("SIGTERM")
      reject(new Error(`codebase-memory-mcp cli timed out after ${DS_CLI_TIMEOUT_MS}ms`))
    }, DS_CLI_TIMEOUT_MS)
    proc.stdout.on("data", (c: Buffer) => (out += c.toString("utf8")))
    proc.stderr.on("data", (c: Buffer) => (err += c.toString("utf8")))
    proc.on("error", (e) => {
      clearTimeout(timer)
      reject(e)
    })
    proc.on("close", (code) => {
      clearTimeout(timer)
      if (code === 0) resolve(out)
      else reject(new Error(`codebase-memory-mcp cli exited ${code}: ${err.trim().slice(0, 300)}`))
    })
  })
}

// Default CLI output is the unwrapped payload JSON (cli_print_mcp_result
// extracts content[0].text): {"projects":[{"name","root_path"},...], ...}.
// Errors go to stderr with a nonzero exit (rejected by runDsCli above).
async function dsProjects(): Promise<DsProject[]> {
  if (dsCache && Date.now() - dsCache.at < DS_CACHE_TTL_MS) return dsCache.projects
  const stdout = await runDsCli()
  const list = JSON.parse(stdout)?.projects
  if (!Array.isArray(list)) throw new Error("cli output has no projects array")
  const projects = list
    .filter((p: unknown): p is { name: string; root_path: string } =>
      typeof (p as any)?.name === "string" && typeof (p as any)?.root_path === "string")
    .map((p) => ({ name: p.name, root: p.root_path.replace(/\/+$/, "") }))
  dsCache = { at: Date.now(), projects }
  return projects
}

// Per-session injection budget, persisted in MySQL (survives restarts and is
// consistent across machines sharing the DB). Atomically claims a slot: the
// conditional UPDATE takes a row lock, so concurrent calls cannot overshoot.
const DS_INJECT_LIMIT = 3

async function dsInjectAllowed(
  pool: mysql.Pool,
  sessionId: string,
  project: string,
  content: string,
): Promise<boolean> {
  const [updated]: any = await pool.query(
    `UPDATE \`${INJECT_TABLE}\` SET inject_count = inject_count + 1, inject_content = ?
     WHERE session_id = ? AND project_name = ? AND inject_count < ?`,
    [content, sessionId, project, DS_INJECT_LIMIT],
  )
  if (updated.affectedRows > 0) return true
  try {
    await pool.query(
      `INSERT INTO \`${INJECT_TABLE}\` (session_id, project_name, inject_count, inject_content) VALUES (?, ?, 1, ?)`,
      [sessionId, project, content],
    )
    return true
  } catch (err: any) {
    if (err?.code === "ER_DUP_ENTRY") return false // row exists and is at the limit
    throw err
  }
}

// Returns the hint line to append, or null (not a code search / no matching
// project / session budget exhausted / any failure — failures log WARN and
// inject nothing).
async function depSearchHint(searchRoot: string, include: string, sessionId: string): Promise<string | null> {
  if (!extractExts(include).some((e) => CODE_EXTS.has(e))) return null
  try {
    const projects = await dsProjects()
    const root = searchRoot.replace(/\/+$/, "")
    let best: DsProject | null = null
    for (const p of projects) {
      if ((root === p.root || root.startsWith(p.root + "/")) && (!best || p.root.length > best.root.length)) {
        best = p
      }
    }
    if (!best) return null
    const pool = await db()
    if (!pool) return null // budget lives in MySQL; recording disabled => injection disabled
    const hint =
      `[dep_search]: this code is indexed. ` +
      `For faster structural code search, use the dep_search_* tools with project "${best.name}".`
    if (!(await dsInjectAllowed(pool, sessionId, best.name, hint))) return null
    return hint
  } catch (err) {
    logWarn(`dep_search hint failed: ${String(err)}`)
    return null
  }
}

// ---------- search (verbatim copy of the built-in grep tool) ----------

function truncateLine(content: string, maxLength = 2000): string {
  if (content.length <= maxLength) return content
  const truncated = content.substring(0, maxLength)
  const lastNewline = truncated.lastIndexOf("\n")
  if (lastNewline > maxLength * 0.7) return truncated.substring(0, lastNewline) + "..."
  return truncated + "..."
}

async function search(pattern: string, include: string, searchPath: string) {
  const args = ["--no-config", "--json", "--hidden", "--no-messages"]
  args.push(`--glob=${include}`)
  if (!filterDisabled()) {
    for (const p of GEN_FILE_PATTERNS) args.push(`--glob=!${p}`)
  }
  args.push("--glob=!**/.git/**")
  args.push("--")
  args.push(pattern)
  args.push(".")

  const proc = spawn("rg", args, { cwd: searchPath, stdio: ["ignore", "pipe", "pipe"] })

  let output = ""
  let errorOutput = ""
  const decoder = new StringDecoder("utf8")

  proc.stdout.on("data", (chunk: Buffer) => {
    output += decoder.write(chunk)
    if (output.length > 1024 * 1024) {
      proc.kill("SIGTERM")
    }
  })

  proc.stderr.on("data", (chunk: Buffer) => {
    errorOutput += decoder.write(chunk)
  })

  const exitCode: number = await new Promise((resolve, reject) => {
    proc.on("close", (code) => resolve(code ?? 0))
    proc.on("error", reject)
  })

  if (errorOutput.trim() && exitCode !== 0) {
    throw new Error(`ripgrep error: ${errorOutput.trim()}`)
  }
  if (exitCode === 2) {
    throw new Error(`ripgrep error: ${errorOutput.trim() || "Search failed"}`)
  }

  const matches: Array<{ path: string; modTime: number; lineNum: number; lineText: string }> = []

  for (const line of output.trim().split("\n")) {
    if (!line) continue
    try {
      const data = JSON.parse(line)
      if (data.type !== "match") continue
      const filePath = data.data.path.text
      const stats = fs.statSync(path.join(searchPath, filePath))
      matches.push({
        path: filePath,
        modTime: stats.mtime.getTime(),
        lineNum: data.data.line_number,
        lineText: truncateLine(data.data.lines.text.trim()),
      })
      if (matches.length >= LIMIT) break
    } catch {
      continue
    }
  }

  if (matches.length === 0) {
    return { searchRoot: searchPath, matches: 0, truncated: false, output: "No files found" }
  }

  matches.sort((a, b) => b.modTime - a.modTime)

  const byFile = new Map<string, typeof matches>()
  for (const m of matches) {
    const list = byFile.get(m.path) ?? []
    list.push(m)
    byFile.set(m.path, list)
  }

  const lines = [`Found ${matches.length} matches`]
  let currentFile = ""
  let numMatches = 0
  for (const m of matches) {
    if (currentFile !== m.path) {
      if (currentFile !== "") lines.push("")
      lines.push(`${m.path}:`)
      currentFile = m.path
    }
    numMatches++
    if (numMatches < LIMIT) lines.push(`  Line ${m.lineNum}: ${m.lineText}`)
  }

  if (matches.length >= LIMIT) {
    lines.push("")
    lines.push("(Results truncated. Consider using a more specific path or pattern.)")
  }

  return {
    searchRoot: searchPath,
    matches: matches.length,
    truncated: matches.length >= LIMIT,
    output: lines.join("\n"),
  }
}

function resolveSearchRoot(searchPath: string | undefined, directory: string): string {
  if (!searchPath) return directory
  return path.isAbsolute(searchPath) ? searchPath : path.resolve(directory, searchPath)
}
