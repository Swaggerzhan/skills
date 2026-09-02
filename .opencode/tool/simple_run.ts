// Custom tool `simple_run`: executes whitelisted binaries (git, openspec, ls)
// with literal argv via execFile. No shell, so pipes, redirects, and arbitrary
// commands are structurally impossible. ls is fixed to `ls -al <absolute path>`.
// The tool id is "simple_run" (the file name), which is also the permission key.

import { execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)

const WHITELIST = new Set(["git", "openspec", "ls"])

export default {
  description:
    "Run a simple whitelisted command: git, openspec, or ls. ls always runs as `ls -al <path>` and only accepts absolute paths.",
  args: {
    command: {
      type: "string",
      description: "Command to run, one of: git, openspec, ls",
    },
    args: {
      type: "array",
      items: { type: "string" },
      description: "Arguments for the command. For ls: absolute path(s) to list",
    },
  },
  async execute(input: { command: string; args?: string[] }, ctx: { directory: string }) {
    const { command, args = [] } = input
    if (!WHITELIST.has(command)) {
      return `command not allowed: ${command} (whitelist: git, openspec, ls)`
    }
    // ls is fixed to `ls -al`; requiring absolute paths also blocks flag
    // injection, since an argument starting with "/" is never parsed as a flag.
    let argv = args
    if (command === "ls") {
      if (args.length === 0 || args.some((a) => !a.startsWith("/"))) {
        return "ls requires an absolute path as its argument"
      }
      argv = ["-al", ...args]
    }
    try {
      const out = await exec(command, argv, {
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
