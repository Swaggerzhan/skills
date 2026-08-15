# Unit-Test Annotation Format (Header / Case Comments)

Purpose: make "what this file tests, which category each case belongs to, and how far it is implemented" extractable by a script and checkable for consistency in CI.

The annotation weight scales with the tier (see `SKILL.md`):

- **Solitary** (no dependencies): light. Hierarchy is **Category → Case**, no Branch, no `@Deps`. Each case still gets a CASE block, but a light one — `@Case` + `@Status`; `@Setup` is not used and `@Detail` is optional.
- **Sociable / Integration** (complex, has dependencies): full. Hierarchy is **Category → Branch → Case**, with `@Deps` and, for the non-trivial cases, `@Setup` / `@Detail`.

## 1. Two Block Types + Paired Anchors

- **File level (HEADER)**: `// @UT-HEADER-BEGIN` … `// @UT-HEADER-END`, one block per test file, placed after the includes and before the first fixture. Required.
- **Case level (CASE)**: `// @UT-CASE-BEGIN` … `// @UT-CASE-END`, one block ("head") for every case. It carries the case's `@Status` so the state is readable straight from the file. Once implemented, the head sits directly above its `TEST_F` / `TEST_P`; a designed-but-unimplemented case (`@Status: todo`) has a head that stands alone, with no `TEST_F` yet.

Anchors are reserved sentinels and must occupy their own line. The `@UT-` prefix + all-caps + hyphens does not occur in normal code or prose, which avoids collisions.

## 2. Level and Symbol Conventions

- `@` is used only at the **outermost** level: the direct fields of Header/Case (`@Unit` `@Tier` `@Deps` `@Desc` `@Case` `@Detail` `@Setup` `@Status`) and the Category anchors (`@Category-BEGIN/END`).
- `*` is used for the **inner** tree inside the Header: `* Branch`, `* Case`.
- Hierarchy: **Category → Branch → Case** for sociable/integration; **Category → Case** for solitary.

### Branch Id

A branch id is a category prefix plus a number that **restarts within each category**:

| Category | Prefix | Ids |
|---|---|---|
| Positive | `BP` | `BP1`, `BP2`, … |
| Recovery | `BR` | `BR1`, `BR2`, … |
| Negative | `BN` | `BN1`, `BN2`, … |

Numbering each category independently keeps changes local: adding or removing a branch in
one category does not renumber the others. Append new branches at the end of their
category (e.g. add `BP7` after `BP6`) rather than inserting and shifting existing ids.
`@Detail` may reference a branch by its id (e.g. `covers BR1`).

## 3. Line-Wrap Safety: the Core Rule

**Any key the machine must recognize is a single short token on the marker line and never wraps; only human-facing descriptions may wrap.**

- `* Branch <Id>:` — `<Id>` (BP1/BR1/BN1…, see §Branch Id) is on the marker line, a single token; the description after `:` may wrap.
- `* Case:` — the value is only the gtest case name (single token) and does not wrap; the explanation for that case goes in the CASE block's `@Detail`.
- When a description wraps, any following `//` line that is not a new marker (does not start with `*` / `@`) is treated as a continuation of the previous entry and is joined by the script.
- The only writing restriction: continuation text must not start with `*` or `@`.

### Multi-line lists (@Detail / @Setup / @Args)

Long `@Setup` / `@Detail` / `@Args` are hard to read on one line, so they may be written as a bullet list. The rule:

- A continuation line that starts with `- ` begins a **new list item**, kept on its own line.
- Any other continuation line **wraps** the current item and is space-joined into it.

```cpp
// @Setup:
//   - create a source POSIX file
//   - configure the object-store mock, and note that a long item
//     can wrap onto the next line
//   - inject a transient write error into tikv
```

This keeps the field human-readable while staying parseable — these fields are human-facing only and are never used as machine keys.

So the case names from `grep '* Case:'` are unaffected by wrapped descriptions.

## 4. HEADER Block — Sociable / Integration

```cpp
// @UT-HEADER-BEGIN
// @Unit: DataServiceTest
// @Tier: integration                       // solitary | component | integration
// @Deps: object_store(mock), master(mock), tikv(inject)
// @Desc: coverage analysis of POSIX-file copy paths into object storage.
//
// @Category-BEGIN: Positive
//   * Branch BP1: copy a POSIX file to a new object while preserving
//     its source metadata -- if the description does not fit, keep
//     wrapping like this and the script joins these lines into BP1's
//     full description.
//     * Case: posix_file_copy_to_object_storage
//   * Branch BP2: copy a POSIX file over an existing object
//     * Case: posix_file_overwrite_object_storage
// @Category-END: Positive
//
// @Category-BEGIN: Recovery
//   * Branch BR1: retry after a transient tikv write error and complete the copy
//     * Case: posix_file_copy_to_object_storage_after_retry
// @Category-END: Recovery
//
// @Category-BEGIN: Negative
//   * Branch BN1: an invalid object key is rejected with EINVAL
//     * Case: (todo)
// @Category-END: Negative
// @UT-HEADER-END
```

## 5. HEADER Block — Solitary

No `@Deps`, no `* Branch`; cases hang directly under the category.

```cpp
// @UT-HEADER-BEGIN
// @Unit: PerculatorUtilsTest
// @Tier: solitary
// @Desc: error-code to message mapping.
//
// @Category-BEGIN: Positive
//   * Case: maps_known_codes_to_message
//   * Case: maps_unknown_code_to_default
// @Category-END: Positive
// @UT-HEADER-END
```

HEADER fields:

- `@Unit`: the gtest test suite / fixture name — the whole test's name, e.g. `PerculatorUtilsTest`. It is the first argument of the `TEST_F` / `TEST_P` macros in the file.
- `@Tier`: the tier, controlled vocabulary `solitary | component | integration`.
- `@Deps`: dependencies and how each is replaced, `name(type)`, where type ∈ `mock | inject`. Omit for solitary.
- `@Desc`: one-line, file-level description.
- `@Args`: for parameterized tests (`TEST_P`), what the parameters mean. Optional; omit when the file has no `TEST_P`. May wrap.
- `@Category-BEGIN/END: <Name>`: a category section, `<Name>` ∈ `Positive | Recovery | Negative`.
- `* Branch <Id>: <description>`: one line per branch, `<Id>` a single token (`BP`/`BR`/`BN` + per-category number, see §Branch Id), description may wrap. Sociable/integration only.
- `* Case: <case-name>`: the gtest case name. Under a `* Branch` for sociable/integration, directly under the category for solitary. `(todo)` means a case is planned but not created yet.

`TEST_P` (parameterized) is treated exactly like `TEST_F`: the case name is its second
macro argument, and it is what a `* Case` entry refers to.

## 6. CASE Block (one per case)

Every case has a CASE block. It is what makes each case's status readable in the file.
For an implemented case the block sits directly above its `TEST_F` / `TEST_P`; for a
designed-but-unimplemented case the block stands alone with `@Status: todo`.

```cpp
// @UT-CASE-BEGIN
// @Case:   posix_file_copy_to_object_storage
// @Status: done
// @Detail: covers BP1 -- copy the source POSIX file into a new object and preserve its metadata.
// @Setup:
//   - create a source POSIX file
//   - configure the object-store mock to accept the upload
//   - inject the destination mapping through tikv
// @UT-CASE-END
TEST_F(DataServiceTest, posix_file_copy_to_object_storage) {
```

A light head, for a trivial (e.g. solitary) case:

```cpp
// @UT-CASE-BEGIN
// @Case:   maps_known_codes_to_message
// @Status: done
// @UT-CASE-END
TEST_F(PerculatorUtilsTest, maps_known_codes_to_message) {
```

CASE fields:

- `@Case`: this case's name; must match the `TEST_F` / `TEST_P` name directly below (when implemented) and be registered as a `* Case` in the HEADER. Required.
- `@Status`: `todo | done`. Required — this is how the case's state is read.
- `@Detail`: the meaning of this case -- what it verifies and expects. May be a multi-line list (§3). Optional; omit when the case name already says it.
- `@Setup`: preconditions / mocks. May be a multi-line list (§3). Not used for solitary.

## 7. Status

Status is read directly from each case, no guessing:

- a case's status is its CASE block `@Status` (`todo | done`);
- a HEADER `* Case: (todo)` placeholder — a slot whose case is not created yet — counts as **todo**;
- `@Status: done` requires a matching `TEST_F` / `TEST_P` directly below the head; `@Status: todo` may stand alone.

A branch whose cases are a mix of done and todo rolls up to **partial**.

The single source of truth for classification is the HEADER (Category → [Branch →] Case); the CASE block does **not** repeat `@Category`. A case's category is derived from the section it belongs to in the HEADER, avoiding drift between two places.
