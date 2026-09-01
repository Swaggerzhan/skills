// Custom tool `simple_run`: executes exactly two whitelisted binaries (git,
// openspec) with literal argv via execFile. No shell, so pipes, redirects,
// and arbitrary commands are structurally impossible. The tool id is
// "simple_run" (the file name), which is also the permission key.

import { execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)

const WHITELIST = new Set(["git", "openspec"])

export default {
  description: "Run a simple whitelisted command: git or openspec, with arguments.",
  args: {
    command: {
      type: "string",
      description: "Command to run, one of: git, openspec",
    },
    args: {
      type: "array",
      items: { type: "string" },
      description: "Arguments for the command",
    },
  },
  async execute(input: { command: string; args?: string[] }, ctx: { directory: string }) {
    const { command, args = [] } = input
    if (!WHITELIST.has(command)) {
      return `command not allowed: ${command} (whitelist: git, openspec)`
    }
    try {
      const out = await exec(command, args, {
        cwd: ctx.directory,
        timeout: 120_000,
        maxBuffer: 10 * 1024 * 1024,
      })
      return [out.stdout?.trim(), out.stderr?.trim()].filter(Boolean).join("\n") || "(no output)"
    } catch (err) {
      const e = err as { stdout?: string; stderr?: string; code?: unknown }
      return [
        e.stdout?.trim(),
        e.stderr?.trim(),
        `${command} failed (exit code ${e.code ?? "unknown"})`,
      ]
        .filter(Boolean)
        .join("\n")
    }
  },
}
