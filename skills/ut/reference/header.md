# Unit-Test Annotation Format (Header / Case Comments)

Purpose: make "what this file tests, which category and branch each case belongs to, and how far it is implemented" extractable by a script and checkable for consistency in CI — while keeping the test file itself readable.

Three rules do most of the work:

1. **One grammar for every tier.** `@Tier` is a descriptive label, not a format switch. Branches are an optional grouping layer in any tier; `@Deps` is written whenever the test replaces dependencies, regardless of tier.
2. **The HEADER is the single source of truth for classification.** A case's category and branch come from where it sits in the HEADER tree — never repeated elsewhere.
3. **Status is derived, never written.** A case with a `TEST_F` / `TEST_P` is `done`; a HEADER case without one is `todo`. There is no status field to keep in sync.

## 1. HEADER Block (one per file)

`// @UT-HEADER-BEGIN` … `// @UT-HEADER-END`, each on its own comment line, placed after the includes and before the first fixture. Required.

```cpp
// @UT-HEADER-BEGIN
// @Unit: CacheServiceTest
// @Tier: sociable
// @Deps: store(mock), clock(inject)
// @Desc: cache reads, refreshes, and retry behavior.
//
// @Category-BEGIN: Positive
//   * Branch BP1: serve a cached value or refresh it when its lifetime
//     has expired.
//     * Case: reads_cached_value
//     * Case: refreshes_expired_value
//       - replaces an expired value from the backing store
// @Category-END: Positive
//
// @Category-BEGIN: Negative
//   * Branch BN1: reject an invalid cache key.
//     * Case: (todo)
// @Category-END: Negative
// @UT-HEADER-END
```

HEADER fields:

- `@Unit`: the gtest fixture / suite name — the first argument of the `TEST_F` / `TEST_P` macros in the file. Required.
- `@Tier`: `solitary | sociable | integration`. Required, informational — it changes no rule in this format.
- `@Deps`: dependencies and how each is replaced, `name(type)`, type ∈ `mock | inject`, comma-separated. Write it when the test replaces dependencies; omit it otherwise.
- `@Desc`: one-line, file-level description. Required.
- `@Args`: for parameterized tests (`TEST_P`), what the parameters mean. Optional; omit when the file has no `TEST_P`. May be a list (§3).
- `@Category-BEGIN/END: <Name>`: a category section, `<Name>` ∈ `Positive | Recovery | Negative`. Every case lives in exactly one category.
- `* Branch <Id>: <description>`: an optional grouping of cases that cover one distinct path through the code under the category. `<Id>` is a category prefix + number: `BP` (Positive), `BR` (Recovery), `BN` (Negative), numbering restarts per category and new branches append at the end (§Branch Id below). The description is required and may wrap. A category may mix branches and direct cases.
- `* Case: <case-name>`: the gtest case name (single token, never wraps), under a branch or directly under the category. `(todo)` means a slot whose case isn't named yet.
- **Design notes**: indented `- ` lines under a `* Case:` describe a case that is not implemented yet — this is where `/ut design` records what the case must do. Once the `TEST_F` exists, the notes must move out of the HEADER into the case head (§2); keeping them in both places is an error.

### Branch Id

| Category | Prefix | Ids |
|---|---|---|
| Positive | `BP` | `BP1`, `BP2`, … |
| Recovery | `BR` | `BR1`, `BR2`, … |
| Negative | `BN` | `BN1`, `BN2`, … |

Per-category numbering keeps changes local: adding or removing a branch in one category does not renumber the others. A case head's `@Detail` may reference a branch by its id (e.g. `covers BR1`).

## 2. Case Head (optional, per case)

A head is a run of `//` comment lines **directly above** a `TEST_F` / `TEST_P` — no blank line between. It carries no name and no status: the name comes from the macro below, and status is derived. Write a head only when there is something worth saying; a case that needs no explanation has no head.

```cpp
// @Detail:
//   - fail the first backing-store request with a transient error
//   - verify that the retry succeeds and returns the requested value
// @Setup:
//   - configure the store mock to fail once
//     and then return a value
//   - inject a stable clock value
TEST_F(CacheServiceTest, retries_transient_store_failure) {
```

Head fields:

- `@Detail`: what the case verifies and expects. Optional; omit when the case name already says it.
- `@Setup`: preconditions / mocks. Optional.

Rules:

- Markers are flush-left: `@Detail:` / `@Setup:` start immediately after `// ` (see §3 for why).
- Ordinary comments may share the comment block with a head — a flush-left line that is not a field marker is not part of the head.
- A head field written anywhere else (not directly above a test macro) is an error — the tool reports it as *dangling*.
- Any field other than `@Detail` / `@Setup` is an error in a head. In particular `@Case` and `@Status` no longer exist: the macro supplies the name, derivation supplies the status.

## 3. Line-Wrap Safety: One Rule Everywhere

**Any key the machine must recognize is a single short token on the marker line and never wraps; only human-facing descriptions may wrap, and every continuation line is indented.**

- `@Unit:`, `* Branch <Id>:`, `* Case:` — values are single tokens on the marker line.
- When a description (`* Branch` text, `@Desc`, `@Args`, `@Detail`, `@Setup`, design notes) continues on following lines:
  - an indented line starting with `- ` begins a **new list item**, kept on its own line;
  - any other indented line **wraps** the current item and is space-joined into it.
- Indentation is what makes a line a continuation. A flush-left `//` line is never a continuation — inside the HEADER that is an error (*orphan continuation*), above a test macro it is simply an ordinary comment. This is what stops a stray comment like `// added in PR #123` from being swallowed into a `@Detail`.

```cpp
// @Setup:
//   - configure the store mock to fail once
//     and then return a value        <- indented wrap: joins the previous item
//   - inject a stable clock value    <- "- " starts a new item
```

The only writing restriction: continuation text must be indented, and a continuation line must not itself start with a marker (`@Word:` flush-left, `* Branch`, `* Case`).

## 4. HEADER Block — Flat (No Branches)

Branches are optional. When the case list is short — typical for solitary tests — cases hang directly off the category:

```cpp
// @UT-HEADER-BEGIN
// @Unit: ParserLogicTest
// @Tier: solitary
// @Desc: parsing and validation of individual values.
//
// @Category-BEGIN: Positive
//   * Case: parses_valid_value
// @Category-END: Positive
//
// @Category-BEGIN: Negative
//   * Case: rejects_empty_value
//     - rejects the empty value with kInvalidArgument and consumes no input
//   * Case: (todo)
// @UT-HEADER-END
```

`TEST_P` (parameterized) is treated exactly like `TEST_F`: the case name is its second macro argument, and it is what a `* Case` entry refers to.

## 5. Status

Status is read from the code, not from a field:

- a case whose name has a `TEST_F` / `TEST_P` is **done**;
- a HEADER `* Case:` with no matching macro is **todo** (as is a `(todo)` placeholder slot);
- a branch whose cases are a mix of done and todo rolls up to **partial**.

Consistency is checked in the other direction too: a `TEST_F` / `TEST_P` whose case name is not registered as a `* Case` in the HEADER is an error, so the tree and the code can never silently drift apart.
