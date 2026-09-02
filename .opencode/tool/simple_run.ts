// Custom tool `simple_run`: executes whitelisted binaries (git, openspec, ls,
// rm, rmdir) with literal argv via execFile. No shell, so pipes, redirects, and
// arbitrary commands are structurally impossible. ls is fixed to
// `ls -al <absolute path>`, rm to `rm -f <absolute path>`, rmdir to
// `rmdir <absolute path>` (removes empty directories only).
// All parameters are scalars because the TUI's generic-tool title renders only
// primitive (string/number/boolean) inputs — an array parameter would be
// invisible there. The tool id is "simple_run" (the file name), which is also
// the permission key.

import { execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)

const WHITELIST = new Set(["git", "openspec", "ls", "rm", "rmdir"])

// Splits an argument string on whitespace, grouping double- or single-quoted
// segments. No escapes or expansion: this only decides argv boundaries and is
// never interpreted by a shell.
function splitArgv(input: string): string[] {
  const out: string[] = []
  for (const m of input.matchAll(/"([^"]*)"|'([^']*)'|(\S+)/g)) {
    out.push(m[1] ?? m[2] ?? m[3])
  }
  return out
}

export default {
  description:
    "Run a simple whitelisted command: git, openspec, ls, rm, or rmdir. ls, rm, and rmdir take `path` (absolute paths only): ls runs as `ls -al <path>`, rm as `rm -f <path>`, rmdir as `rmdir <path>` (removes empty directories only). git and openspec take `args`, one argument string; quote any argument containing spaces, e.g. `commit -m \"message\"`.",
  args: {
    command: {
      type: "string",
      description: "Command to run, one of: git, openspec, ls, rm, rmdir",
    },
    path: {
      type: "string",
      description: "Absolute path. Required by ls, rm, and rmdir; ignored otherwise",
    },
    args: {
      type: "string",
      description:
        'Argument string for git or openspec, e.g. `status --short` or `commit -m "message"`. Quote arguments containing spaces',
    },
  },
  async execute(input: { command: string; path?: string; args?: string }, ctx: { directory: string }) {
    const { command } = input
    if (!WHITELIST.has(command)) {
      return `command not allowed: ${command} (whitelist: git, openspec, ls, rm, rmdir)`
    }
    let argv: string[]
    if (command === "git" || command === "openspec") {
      argv = splitArgv(input.args ?? "")
    } else {
      // Requiring absolute paths also blocks flag injection, since an argument
      // starting with "/" is never parsed as a flag.
      const path = input.path ?? ""
      if (!path.startsWith("/")) {
        return `${command} requires an absolute path in the "path" argument`
      }
      if (command === "ls") argv = ["-al", path]
      else if (command === "rm") argv = ["-f", path]
      else argv = [path] // rmdir itself refuses non-empty directories
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
