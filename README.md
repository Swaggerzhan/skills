# Skills and Rules

## Install Skills from This Repository

Install one Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill cpp-coding-style
```

Install every Skill:

```bash
npx skills add https://github.com/Swaggerzhan/skills --skill '*'
```

## Install Rules from This Repository

```bash
npx rulesync init
npx rulesync add Swaggerzhan/skills --rules answer
npx rulesync generate --features rules
```

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

Commands operate on the current project by default. Add `-g` to operate on globally installed Skills.

List project Skills:

```bash
npx skills ls
```

List global Skills:

```bash
npx skills ls -g
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
