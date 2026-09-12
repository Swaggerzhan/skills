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
      output: result.output,
      error: null,
    })
    return {
      title: pattern!,
      metadata: { matches: result.matches, truncated: result.truncated },
      output: result.output,
    }
  },
})

// ---------- record store (MySQL) ----------

type Config = { host: string; port: number; user: string; password: string; database: string; table: string }

const REQUIRED_ENV = [
  "OPENCODE_AGREP_MYSQL_ENDPOINT",
  "OPENCODE_AGREP_MYSQL_USERNAME",
  "OPENCODE_AGREP_MYSQL_PASSWORD",
  "OPENCODE_AGREP_MYSQL_DATABASE_NAME",
  "OPENCODE_AGREP_MYSQL_TABLE_NAME",
] as const

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
    table: env.OPENCODE_AGREP_MYSQL_TABLE_NAME!,
  }
  return cached
}

let ready: Promise<{ pool: mysql.Pool; table: string } | null> | undefined

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
        await pool.query(`CREATE TABLE IF NOT EXISTS \`${cfg.table}\` (
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
        return { pool, table: cfg.table }
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
  const conn = await db()
  if (!conn) return
  try {
    await conn.pool.query(
      `INSERT INTO \`${conn.table}\` (session_id, agent, directory, pattern, path, include, intent, matches, truncated, output_text, error)
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
