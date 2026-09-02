---
name: ut
description: Workflow and commands for writing unit tests.
disable-model-invocation: true
---

This skill is invoked as `/ut <command> [args]`. The commands share one model of a
unit test (§Concepts) and one on-disk annotation format (§Annotation Format,
`reference/header.md`), inspected with `scripts/cli.py` (§Reading a Test File).

## Guiding Principle: Branch Coverage

The tests this skill produces are **branch-coverage driven**: the goal is to exercise as
many distinct branches of the code under test as possible, not just to hit a happy path.
When designing or extending a test, enumerate the code's decision points — conditionals,
early returns, error/edge cases, state transitions, boundary values — and make sure each
one is covered by at least one case. A feature is "well tested" here when its branches are
covered, not when it merely has some passing cases. This is why cases are grouped under
**branches** (§Concepts): a branch is a distinct path to be covered, and the summary
rolls case status up per branch so uncovered or partial branches stand out.

## Commands

### `/ut design [desc]`

`desc` describes a module or piece of code to be unit-tested. Analyze that code and
produce a **test design**, not test bodies:

- which **tier** the test should be (§Tier);
- the dependencies and how each is replaced (`mock` or `inject` — see Concepts); solitary has none;
- the cases to cover, grouped by **category** (Positive / Recovery / Negative) — and, where
  the case list calls for it (typical for sociable/integration), grouped under **branches**
  within each category.

Drive the design by branch coverage: walk the code under test and list its decision
points (conditionals, early returns, error paths, boundaries, state transitions), then
turn each into a branch/case so no reachable path is left uncovered.

Write the result following `reference/header.md`: the HEADER block with a `* Case:` entry
per planned case (indented `- ` lines under an entry hold its design notes) and
`* Case: (todo)` for slots whose case isn't named yet. At this stage there are no `TEST_F`
bodies — the HEADER alone carries the design.

### `/ut impl [test-file]`

`test-file` already contains a prepared HEADER. If no file is given, ask the user.

1. Run `--op summary` to see which cases are `todo`.
2. For each, run `--op case --case_name <name>` and read its detail and setup notes
   to learn what the case must do and how to set it up.
3. Implement each case: write the `TEST_F` / `TEST_P` — a case turns `done` simply by
   having its macro; there is no status field to flip. If the case has design notes in
   the HEADER that are worth keeping, move them into a head (`@Detail` / `@Setup`)
   directly above the macro; keeping them in the HEADER as well is an error.

If a description is unclear, ask the user or find the answer in the production code.
If you hit an unreasonable design, stop and raise it with the user instead of forcing it.

### `/ut adopt [test-file]`

Bring an existing test (written before this skill) under the annotation system.
**Do not modify the test directly first.** Instead:

1. Analyze the file and produce a report: which tier it is, and which
   categories / branches / cases it currently covers.
2. Only after the user approves, write the HEADER and any case heads into the file.

### `/ut update [test-file]`

Extend an existing annotated test: add cases that are still `todo` or uncovered, or
revise an existing case. Start with `--op summary` to find the gaps, then design +
implement as in `impl`, keeping the HEADER in sync.

### `/ut` or `/ut help`

No command: print this usage.

## Concepts

A unit test breaks into two things: the **test** and its **cases**.

- The **test** covers one feature or module — small and self-contained, or a large
  process-level module. Before adding one, decide its **tier**.
- The **cases** are the concrete `TEST_F` scenarios inside it. Once the tier is fixed,
  design the cases.

### Tier

The tier is the kind of test. Pick it before writing.

| Tier | Name | What it tests |
|---|---|---|
| 1 | Solitary unit test | Self-contained logic, input to output. Crosses no boundary. |
| 2 | Sociable unit test | The object under test plus a few dependencies (real or faked). No RPC/network boundary. |
| 3 | Integration test | A real service driven through its service paths, with faked external dependencies. May cross RPC/Raft/process boundaries. |

Pick the lowest tier that verifies the behavior reliably. Go higher only when the
behavior itself needs that tier's collaborators or boundaries.

### Cases

Each case belongs to a **category** — the kind of path it verifies.

| Category | What it verifies |
|---|---|
| Positive | Valid input, normal path, succeeds. |
| Recovery | A recoverable fault is injected; the system self-heals and still succeeds. |
| Negative | Invalid input is rejected with a definite error; no recovery. |

Within a category, a **branch** groups cases that cover one distinct path through the
code under that category. Branches are an optional grouping layer in every tier —
**Category → Case** or **Category → Branch → Case**, the grammar is the same. Solitary
tests usually hang cases directly off the category; for sociable/integration tests, aim
to enumerate every meaningful branch — the coverage target is branches, not case count.

The **case** is the concrete `TEST_F` (or `TEST_P` for a parameterized test).

### Dependencies

When a test cannot use a real dependency, it replaces it one of two ways:

- **mock**: a stand-in the test controls — for example a fake RPC mock, or a subclass that overrides methods.
- **inject**: a behavior or fault injected into the production code through a `#UNITEST` hook. This reaches into production code, so use it only as a last resort, when there is no other way.

## Annotation Format

The hierarchy is written into the test file as machine-readable comments, so a script
can extract what each file covers and CI can check it. Before writing or annotating a
unit test, read `reference/header.md` and follow that format. In short:

- One grammar for all tiers: a HEADER block at the top of the file carries the
  Category → [Branch →] Case tree plus `@Unit` / `@Tier` / `@Desc`, and `@Deps` when
  the test replaces dependencies.
- Status is derived, never written: a case with a `TEST_F` / `TEST_P` is `done`, a
  HEADER case without one is `todo`.
- Per-case notes are optional: a head is a run of `@Detail` / `@Setup` comment lines
  directly above the macro — write one only when there is something worth saying.
  Design notes for unimplemented cases live in the HEADER as indented `- ` lines under
  the `* Case:` entry.

## Reading a Test File

Use `scripts/cli.py` to read the current state of a test file (standard library only).
Start here before adding cases, so you know what already exists and how far each case is
implemented.

```sh
python3 scripts/cli.py --file <test.cpp> --op summary
```

Shows the file's tier, dependencies, and every category with its cases (grouped under
branches where used), each with its derived completion (`done` / `todo`; a branch with
both rolls up to `partial`).

```sh
python3 scripts/cli.py --file <test.cpp> --op case --case_name <name>
```

Shows one case's category, branch (if any), status, detail, setup, and the `TEST_F` it
maps to; for a `todo` case, the design notes recorded in the HEADER.

```sh
python3 scripts/cli.py --file <test.cpp> --op verify
```

Checks that the annotation format is well-formed (fields present, controlled
vocabularies respected, header cases and `TEST_F` names consistent). Exits non-zero on
any error, so it can run in CI.
