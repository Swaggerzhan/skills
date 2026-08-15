---
name: commit
description: MUST use when creating a Git commit or commit message.
allowed-tools: Bash
---
Run the following commands to understand the current changes:

```
git diff HEAD
git diff --cached
git status
```

Then generate a commit message following these rules:

## Prefix
Choose the most appropriate prefix:
- `bugfix` - fixes a bug or incorrect behavior
- `feat` - adds a new feature
- `enhance` - improves existing functionality without adding new features
- `typo` - fixes typos or comments only
- `refactor` - restructures code without changing behavior
- `test` - adds or updates tests
- `docs` - documentation only
- `chore` - build system, dependencies, config changes

## Format Rules

**Simple change** (small or straightforward): one line only.
```
bugfix: fix null pointer dereference in connection pool
```

**Complex change** (multiple concerns or non-trivial logic): add one blank line, then a `details:` block.
```
feat: add retry mechanism for failed RPC calls

details:
    1. add configurable retry count via gflag
    2. exponential backoff between retries
    3. propagate final error code to caller
```

**Single detail**: write the detail directly without numbering.
```
enhance: reduce memory allocation in hot path

details:
    reuse pre-allocated buffer instead of allocating per request
```

## OpenSpec files

Do not mention openspec file changes in the commit message.
Read openspec changes to better understand the direction of this change.

## Requirements
- Commit message must be in English
- Subject line: concise, imperative mood, no period at end
- Each detail item: plain English, specific, no vague phrases like "fix issue" or "update code"

## After generating the commit message

Output the following sections in order:

### 1. Commit message
Print the commit message text.

### 2. Suggested files to include
List the files that should be staged for this commit, based on the diff and status.
Exclude files that are unrelated to the change (e.g. untracked build artifacts,
temporary files, or changes that belong in a separate commit).

```
Suggested files:
  src/foo.cpp
  include/foo.h
  test/test_foo.cpp
```

### 3. Ready-to-run commands
Print the exact commands the user can run or ask you to run:

```bash
git add src/foo.cpp include/foo.h test/test_foo.cpp
git commit -m "feat: add retry mechanism for failed RPC calls"
```

Then ask: "Run these commands for you, or will you do it yourself?"
