# Project Guide

This repository maintains reusable Skills and opencode-related Markdown/config
documents, including primary agents, subagents, commands, and tools.

When changing configuration, do not edit global user files under `~/.config/`.
Edit the source files in this repository instead:

- opencode configuration and agent/command/tool Markdown: `.opencode/`
- general Skills: `skills/`
- deployable `AGENTS.md` content: `AGENTS_.md`

`AGENTS_.md` uses a trailing underscore so AI agents maintaining this
repository do not load it as project guidance. It is the source file that
should be linked to the target `AGENTS.md` location.
