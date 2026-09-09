# Skills

## Install Skills from This Repository

Install one Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill cpp-coding-style
```

Install every Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill '*'
```

For updates, external Skills and full `npx skills` usage (ls/update/remove), see
[docs/skills_install.md](docs/skills_install.md).

## Optional: Dependency Graph Queries via codebase-memory-mcp

Agents in this repository can additionally query a knowledge graph of external
dependencies (symbol definitions, callers/callees, source snippets) through the
`dep_search_*` MCP tools — generally more efficient than grep for structural
queries. See [docs/codebase-memory-mcp.md](docs/codebase-memory-mcp.md) for how
to install and index the dependency repositories, and how the agents are wired
to use it.
