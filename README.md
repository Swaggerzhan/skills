# Install Skills and Rules

## Install Skills Only

Install one Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill cpp-coding-style
```

Install every Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill '*'
```

## Install Rules Only

`npx skills` does not install Rules. Use [Rulesync](https://github.com/dyoshikawa/rulesync), which reads Rules from this repository's `rules/` directory and generates the native files required by the selected Agents.

```bash
npx rulesync init
npx rulesync add Swaggerzhan/skills --rules answer
npx rulesync generate --features rules
```
