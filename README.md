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

Update project-installed Skills:

```bash
npx skills update -p
```

Update globally installed Skills:

```bash
npx skills update -g
```

Updates are fetched from GitHub. Local changes must be pushed before they can be
installed with `npx skills update`.

## External Skills

Install Anthropic's `skill-creator`:

```bash
npx skills add https://github.com/anthropics/skills --skill skill-creator
```

Install Matt Pocock's `handoff`:

```bash
npx skills add https://github.com/mattpocock/skills --skill handoff
```

## Using npx skills

`ls` and `remove` operate on the current project by default; add `-g` for global Skills.
For `update`, use `-p` for project Skills or `-g` for global Skills.

List project Skills:

```bash
npx skills ls
```

List global Skills:

```bash
npx skills ls -g
```

Update all project Skills:

```bash
npx skills update -p
```

Update one project Skill:

```bash
npx skills update cpp-coding-style -p
```

Update all global Skills:

```bash
npx skills update -g
```

Update one global Skill:

```bash
npx skills update cpp-coding-style -g
```

Remove a project Skill:

```bash
npx skills remove cpp-coding-style
```

Remove a global Skill:

```bash
npx skills remove -g cpp-coding-style
```

Remove all project Skills:

```bash
npx skills remove --all
```

Remove all global Skills:

```bash
npx skills remove --all -g
```

## Optional: Dependency Graph Queries via codebase-memory-mcp

Agents in this repository can additionally query a knowledge graph of external
dependencies (symbol definitions, callers/callees, source snippets) through the
`dep_search_*` MCP tools — generally more efficient than grep for structural
queries. See [docs/codebase-memory-mcp.md](docs/codebase-memory-mcp.md) for how
to install and index the dependency repositories, and how the agents are wired
to use it.
