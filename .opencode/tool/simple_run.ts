// Custom tool `simple_run`: executes whitelisted binaries (git, openspec, ls,
// rm, rmdir) with literal argv via execFile. No shell, so pipes, redirects, and
// arbitrary commands are structurally impossible. ls is fixed to
// `ls -al <absolute path>`, rm to `rm -f <absolute path>`, rmdir to
// `rmdir <absolute path>` (removes empty directories only). rm and rmdir take
// exactly one path argument. The tool id is "simple_run" (the file name),
// which is also the permission key.

import { execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)

const WHITELIST = new Set(["git", "openspec", "ls", "rm", "rmdir"])

export default {
  description:
    "Run a simple whitelisted command: git, openspec, ls, rm, or rmdir. ls, rm, and rmdir accept absolute paths only. ls runs as `ls -al <path>`. rm runs as `rm -f <path>` and rmdir as `rmdir <path>` (removes empty directories only); both take exactly one path argument, no flags or extras.",
  args: {
    command: {
      type: "string",
      description: "Command to run, one of: git, openspec, ls, rm, rmdir",
    },
    args: {
      type: "array",
      items: { type: "string" },
      description:
        "Arguments for the command. ls takes absolute path(s) to list; rm and rmdir take exactly one absolute path",
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
    // rm is fixed to `rm -f <path>` and rmdir to `rmdir <path>`: exactly one
    // absolute path, no other arguments. rmdir itself refuses non-empty
    // directories, so empty-only deletion needs no extra check.
    if (command === "rm" || command === "rmdir") {
      if (args.length !== 1 || !args[0].startsWith("/")) {
        return `${command} requires exactly one absolute path as its argument`
      }
      argv = command === "rm" ? ["-f", args[0]] : args
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
