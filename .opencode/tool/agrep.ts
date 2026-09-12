// Custom tool `agrep`: identical to opencode's built-in grep (same rg invocation,
// same output format, 100-match limit), plus a required `intent` parameter — a
// short phrase stating why the search is needed. Every call is recorded to MySQL
// (input = the 4 parameters, output = the complete result). Empty intent,
// unconfigured env, unreachable DB, or failed insert all fail the call with an
// error fed back to the model. Design: docs/agrep.md.
//
// Config via env: OPENCODE_AGREP_MYSQL_ENDPOINT (host:port, port default 3306),
// OPENCODE_AGREP_MYSQL_USERNAME, OPENCODE_AGREP_MYSQL_PASSWORD,
// OPENCODE_AGREP_MYSQL_DATABASE_NAME, OPENCODE_AGREP_MYSQL_TABLE_NAME.

import { spawn } from "node:child_process"
import fs from "node:fs"
import path from "node:path"
import { StringDecoder } from "node:string_decoder"
import { tool } from "@opencode-ai/plugin"
import mysql from "mysql2/promise"

const LIMIT = 100
const MAX_LINE = 2000

// ---------- MySQL ----------

function getConfig() {
  const endpoint = process.env.OPENCODE_AGREP_MYSQL_ENDPOINT
  const user = process.env.OPENCODE_AGREP_MYSQL_USERNAME
  const password = process.env.OPENCODE_AGREP_MYSQL_PASSWORD
  const database = process.env.OPENCODE_AGREP_MYSQL_DATABASE_NAME
  const table = process.env.OPENCODE_AGREP_MYSQL_TABLE_NAME
  const missing: string[] = []
  if (!endpoint) missing.push("OPENCODE_AGREP_MYSQL_ENDPOINT")
  if (!user) missing.push("OPENCODE_AGREP_MYSQL_USERNAME")
  if (password === undefined) missing.push("OPENCODE_AGREP_MYSQL_PASSWORD")
  if (!database) missing.push("OPENCODE_AGREP_MYSQL_DATABASE_NAME")
  if (!table) missing.push("OPENCODE_AGREP_MYSQL_TABLE_NAME")
  if (missing.length) {
    throw new Error(`agrep: MySQL not configured, missing env: ${missing.join(", ")}`)
  }
  const ep = endpoint!
  const i = ep.lastIndexOf(":")
  return {
    host: i < 0 ? ep : ep.slice(0, i),
    port: i < 0 ? 3306 : Number(ep.slice(i + 1)) || 3306,
    user: user!,
    password: password!,
    database: database!,
    table: table!,
  }
}

// Module-level lazy pool, reused for the opencode process lifetime. A failed
// init clears the cached promise so the next call retries from scratch.
let ready: Promise<{ pool: mysql.Pool; table: string }> | undefined

function db() {
  if (!ready) {
    ready = (async () => {
      const cfg = getConfig()
      const pool = mysql.createPool({
        host: cfg.host,
        port: cfg.port,
        user: cfg.user,
        password: cfg.password,
        database: cfg.database,
      })
      await pool.query(`CREATE TABLE IF NOT EXISTS \`${cfg.table}\` (
  session_id   VARCHAR(64)     NOT NULL,
  seq          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  created_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  agent        VARCHAR(64)     NOT NULL,
  directory    VARCHAR(512)    NOT NULL,
  pattern      TEXT            NOT NULL,
  path         VARCHAR(1024)   NOT NULL,
  \`include\`  VARCHAR(255)    NULL,
  intent       TEXT            NOT NULL,
  matches      INT             NULL,
  truncated    TINYINT(1)      NULL,
  output_text  MEDIUMTEXT      NULL,
  error        TEXT            NULL,
  PRIMARY KEY (session_id, seq),
  KEY idx_seq (seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`)
      return { pool, table: cfg.table }
    })().catch((e) => {
      ready = undefined
      throw e
    })
  }
  return ready
}

type Row = {
  sessionID: string
  agent: string
  directory: string
  pattern: string
  path: string
  include: string | null
  intent: string
  matches: number | null
  truncated: number | null
  output: string | null
  error: string | null
}

async function save(row: Row) {
  const { pool, table } = await db()
  await pool.execute(
    `INSERT INTO \`${table}\` (session_id, agent, directory, pattern, path, \`include\`, intent, matches, truncated, output_text, error)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      row.sessionID,
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
}

// ---------- grep (mirrors packages/opencode/src/tool/grep.ts) ----------

type Match = { path: string; line: number; text: string }

// Resolves the search root the same way the built-in grep does: a missing or
// relative `path` is resolved against the session directory; if it points to a
// file, the search runs in that file's directory.
function resolveSearchRoot(inputPath: string | undefined, directory: string): string {
  const requested = path.isAbsolute(inputPath ?? directory)
    ? (inputPath ?? directory)
    : path.join(directory, inputPath ?? ".")
  let isDir = false
  try {
    isDir = fs.statSync(requested).isDirectory()
  } catch {
    // Unstatable path: fall through and search its parent, like the built-in.
  }
  return isDir ? requested : path.dirname(requested)
}

// Same invocation as the built-in grep:
//   rg --no-config --json --hidden --no-messages [--glob=<include>] --glob=!**/.git/** -- <pattern> .
// Reading stops early once LIMIT matches are collected.
function runRg(cwd: string, pattern: string, include?: string): Promise<Match[]> {
  return new Promise((resolvePromise, reject) => {
    const args = ["--no-config", "--json", "--hidden", "--no-messages"]
    if (include) args.push(`--glob=${include}`)
    args.push("--glob=!**/.git/**", "--", pattern, ".")
    const child = spawn("rg", args, { cwd, stdio: ["ignore", "pipe", "pipe"] })
    const decoder = new StringDecoder("utf8")
    const matches: Match[] = []
    let buf = ""
    let stderr = ""
    let done = false
    const finish = (err?: Error) => {
      if (done) return
      done = true
      if (err) reject(err)
      else resolvePromise(matches)
    }
    child.stdout.on("data", (chunk: Buffer) => {
      buf += decoder.write(chunk)
      let idx: number
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx)
        buf = buf.slice(idx + 1)
        if (!line) continue
        let rec: any
        try {
          rec = JSON.parse(line)
        } catch {
          continue
        }
        if (rec.type !== "match") continue
        const d = rec.data
        const p = d.path.text ?? Buffer.from(d.path.bytes, "base64").toString()
        let text: string = d.lines.text ?? Buffer.from(d.lines.bytes, "base64").toString()
        text = text.replace(/\r?\n$/, "")
        if (text.length > MAX_LINE) text = text.slice(0, MAX_LINE)
        matches.push({ path: p, line: d.line_number, text })
        if (matches.length >= LIMIT) {
          child.kill()
          finish()
          return
        }
      }
    })
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString()
    })
    child.on("error", (e) => finish(new Error(`failed to run rg: ${e.message}`)))
    child.on("close", (code) => {
      // Exit code 1 means "no matches"; code 2 is a real error.
      if (code && code !== 1) return finish(new Error(`rg exited with code ${code}: ${stderr.trim()}`))
      finish()
    })
  })
}

async function grep(cwd: string, pattern: string, include?: string) {
  const matches = await runRg(cwd, pattern, include)
  if (matches.length === 0) return { matches: 0, truncated: false, output: "No files found" }
  const truncated = matches.length === LIMIT
  const out = [`Found ${matches.length} matches${truncated ? " (more matches available)" : ""}`]
  let current = ""
  for (const m of matches) {
    const abs = path.resolve(cwd, m.path)
    if (current !== abs) {
      if (current !== "") out.push("")
      current = abs
      out.push(`${abs}:`)
    }
    out.push(`  Line ${m.line}: ${m.text}`)
  }
  if (truncated) {
    out.push("")
    out.push("(Results truncated. Consider using a more specific path or pattern.)")
  }
  return { matches: matches.length, truncated, output: out.join("\n") }
}

// ---------- tool definition ----------

export default tool({
  description: `- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
- Returns file paths and line numbers with matching lines
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with \`rg\` (ripgrep) directly. Do NOT use \`grep\`.
- When you are doing an open-ended search that may require multiple rounds of globbing and grepping, use the Task tool instead
- The \`intent\` parameter is REQUIRED: a short phrase stating why you need this search (e.g. "get references", "find definition", "understand implementation", "audit usage", "locate error source"). It does not change the search behavior.`,
  args: {
    pattern: tool.schema.string().describe("The regex pattern to search for in file contents"),
    path: tool.schema.string().optional().describe("The directory to search in. Defaults to the current working directory."),
    include: tool.schema.string().optional().describe('File pattern to include in the search (e.g. "*.js", "*.{ts,tsx}")'),
    intent: tool.schema
      .string()
      .describe(
        'Required short phrase stating why you need this search (e.g. "get references", "find definition", "locate error source"). Does not affect the results.',
      ),
  },
  async execute(input, ctx) {
    const root = resolveSearchRoot(input.path, ctx.directory)
    const row: Row = {
      sessionID: ctx.sessionID,
      agent: ctx.agent,
      directory: ctx.directory,
      pattern: input.pattern ?? "",
      path: root,
      include: input.include ?? null,
      intent: input.intent ?? "",
      matches: null,
      truncated: null,
      output: null,
      error: null,
    }
    try {
      if (!input.pattern) throw new Error("pattern is required")
      if (!input.intent?.trim()) {
        throw new Error(
          'intent is required: give a short phrase stating why you need this search (e.g. "get references", "find definition", "locate error source")',
        )
      }
      const result = await grep(root, input.pattern, input.include)
      row.matches = result.matches
      row.truncated = result.truncated ? 1 : 0
      row.output = result.output
    } catch (e) {
      row.error = e instanceof Error ? e.message : String(e)
    }
    // A failed save throws and fails the whole call — by design (docs/agrep.md §4).
    await save(row)
    if (row.error) throw new Error(row.error)
    return {
      title: input.pattern,
      output: row.output!,
      metadata: { matches: row.matches, truncated: row.truncated === 1 },
    }
  },
})
