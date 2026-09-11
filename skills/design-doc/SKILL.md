---
name: design-doc
description: Write a design document for a system change — decisions first, current and target state drawn with system views.
---

# Design Doc

A design doc lays out a change: why it is needed, what the design is, and
how it is implemented. Focus on the design and its implementation — every
section serves that; one that doesn't is cut.

## System views

Draw the current state and the target state with the shared
**system-views** skill — load it first and apply its vocabulary,
renderings, and rules. They are not restated here.

## Skeleton

1. **Background** — why this requirement exists. Only for a large feature;
   for a small one it is waste.
2. **Situation** — the current state. Skip when the design does not
   intersect what exists; describing it then carries no meaning.
3. **Proposed** — the proposal: the target structure — nodes, their
   interactions, the modules inside a node — drawn as system views.
   Several options → present them with a comparison; a single option →
   just that one, no comparison.
4. **Implementation** — data structures first, algorithms after (below).
5. **Capacity estimates** — optional; size the design when scale matters:
   memory usage, persisted size, throughput — numbers with their
   assumptions, not adjectives.
6. **Corner cases** — optional. Where the case hides, and how the design
   disposes of it.
7. **Risks** — each with the condition that triggers it: e.g. a
   structure's complexity under some algorithm, or a possible memory
   blowup.

## Implementation

**Data structures** — state them exactly, in the storage medium's own
terms:

- persisted in a raft state machine → the proto definition, verbatim
- in a database → the SQL schema
- in memory → the project language; an index in C++ is `std::map<xxx, yyy>`

**Algorithms** — pick the few that matter: the longest flows, the ones
that most express the design — judge by what the design hinges on. For a
complex flow, the diagram comes first, then the explanation against it.

## Rules

- when the doc outgrows ~400 lines, split it into a directory named after
  the design: each section becomes a file named after it
- language follows the conversation — write the doc in English or Chinese,
  matching the language the user uses with you
- write only what the design does, straight to the point: no negated
  content ("we will not do X"), no comparisons unless Proposed holds real
  competing options
- cite code by stable symbol (`Class::method`), not `file:line`
- break content that resists prose into steps or itemized lists
- the current state is referenced, not re-explained — the doc's job is the
  change
- contracts are stated exactly (fields, semantics, compatibility), not
  paraphrased
- mark evidence: **Observed** (the code proves it), **Inferred** (from
  evidence), **Unknown** (not decidable yet)
