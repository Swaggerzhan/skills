import { spawn } from "node:child_process"
import os from "node:os"
import path from "node:path"
import { tool } from "@opencode-ai/plugin"

// Clone of the built-in grep tool, plus a required `intent` parameter.
// Thin shell: all heavy logic (rg, filters, dep_search hint, MySQL recording)
// lives in the Go binary; this file only resolves `path`, spawns the binary
// with --name=value flags, and passes the result through. Exit 0 → stdout is
// the result; exit 1 → stdout is the error message to throw back to the model;
// exit 2 → flag-parse error on stderr. The binary is replaced out-of-band, so
// updates ship by swapping OPENCODE_OTOOLS_AGREP_BIN's target file.

const DESCRIPTION = `- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- The \`include\` parameter is REQUIRED: a glob that restricts which files are searched (e.g. "*.cc", "*.{h,hpp,cpp,cc}", or a file name like "Makefile"); a bare "*" is not allowed
- Returns file paths and line numbers with matching lines
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with \`rg\` (ripgrep) directly
- When you are doing an open-ended search that may require multiple rounds of globbing and grepping, use the Task tool instead
- The \`intent\` parameter is REQUIRED: a short phrase in English (just a few words) stating why you need this search (e.g. "get references", "find definition", "understand implementation", "audit usage", "locate error source"). It does not change the search behavior.`

function binPath(): string {
  const env = process.env.OPENCODE_OTOOLS_AGREP_BIN?.trim()
  return env || path.join(os.homedir(), ".local", "bin", "agrep")
}

function resolveSearchRoot(searchPath: string | undefined, directory: string): string {
  if (!searchPath) return directory
  return path.isAbsolute(searchPath) ? searchPath : path.resolve(directory, searchPath)
}

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
    const argv = [
      `--pattern=${args.pattern ?? ""}`,
      `--include=${args.include ?? ""}`,
      `--intent=${args.intent ?? ""}`,
      `--path=${resolveSearchRoot(args.path, context.directory)}`,
      `--session-id=${context.sessionID}`,
      `--message-id=${context.messageID}`,
      `--agent=${context.agent}`,
    ]
    const result = await new Promise<{ code: number; out: string; err: string }>((resolve, reject) => {
      const proc = spawn(binPath(), argv, { stdio: ["ignore", "pipe", "pipe"] })
      let out = ""
      let err = ""
      proc.stdout.on("data", (c: Buffer) => (out += c.toString("utf8")))
      proc.stderr.on("data", (c: Buffer) => (err += c.toString("utf8")))
      proc.on("error", (e) => reject(new Error(`agrep binary spawn failed (${binPath()}): ${e.message}`)))
      proc.on("close", (code) => resolve({ code: code ?? 1, out, err }))
    })
    if (result.code !== 0) {
      throw new Error(result.out.trim() || result.err.trim() || `agrep exited ${result.code}`)
    }
    return {
      title: args.pattern ?? "",
      metadata: {},
      output: result.out,
    }
  },
})
