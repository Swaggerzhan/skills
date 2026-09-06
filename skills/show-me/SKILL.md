---
name: show-me
description: Explain this codebase visually — flow, structure, change, algorithm, concept, or data model.
disable-model-invocation: true
---

# Show Me

This skill is invoked as `/show-me <description>`. The `description` says what the
user wants to understand — a runtime flow, a structural unit, a change, an algorithm,
a concept, or a data model.

Produce a **visual-first** explanation: build a working mental model with a minimal
set of sketches, each sitting right next to the short text it supports. Skip
pleasantries and keep prose lean — the sketches carry the explanation; the text only
frames them.

If the `description` is empty, ask one short question. If it is ambiguous, state your
reading in one sentence and proceed.

## Step 1 — Classify the question

Before reading any code, classify along two axes.

**Question shape** (pick one primary shape):

| Shape | Typical request | Primary model | Default rendering |
|---|---|---|---|
| Flow | "how does X work", "what happens when…", "walk me through" | dynamic view | call tree or sequence diagram |
| Structure | "the architecture of X", "how is X organized", "what modules exist" | static view | layered/component diagram, annotated shallow file tree |
| Logic | "explain this algorithm/function" | dynamic view, single unit | branch narrative |
| Change | "what does this change/PR do", "before vs. after" | delta of two views | diff shape |
| Concept | "what is X in this codebase" | static view + one example flow | small map + one flow |
| Data Model | "how is the data stored", "relations between tables/entities" | static view, data side | erDiagram + entity table |

**Flow vs. Logic.** Both are dynamic; the difference is where the explanatory value
lies. Decide with the boundary test: does answering this question require naming a
**second ownership boundary** (another module, layer, process, or an async
continuation)?

- Yes → **Flow**: model who the participants are and how control, data, and state
  ownership cross those boundaries. Render as a call tree or sequence diagram.
- No — the scenario stays inside a single unit and the difficulty is its internal
  decision structure (branches, early returns, loops, state transitions) →
  **Logic**: render the decisions as a branch narrative.

Each rendering has its place: a flow drawn as a branch narrative hides ownership and
async boundaries; logic drawn as a sequence diagram degenerates into a single
participant. When a single unit's internal logic steps across a boundary and that
crossing is the point of the question, treat it as a small flow.

**Breadth** — narrow (one function, one module, one question) or wide (a subsystem,
a cross-cutting feature, the whole repo). Narrow: explore and explain in one pass.
Wide: map landmarks first, then explain; when components pile up, split into
multiple independent views rather than enlarging a single diagram.

## Step 2 — Explore with intent

Read real code: structural judgments rest only on implementations actually read;
file names and READMEs serve only as locating clues.

- Start from landmarks: manifests, entry points, route/handler registrations, and
  any symbols the request names (grep them).
- Follow the thread from entry to effect. Stop when you can state every step from
  trigger to outcome without hedging.
- **Wide requests**: split into 2–4 orthogonal exploration angles (e.g., data model,
  orchestration, I/O boundaries), **dispatch exploration subagents in parallel**,
  one angle each, then synthesize. Give each subagent a structured return contract —
  responsibilities and connections only, no code dumps:

  ```text
  NODE: camelCaseId
    Label: plain-language name (e.g., "session persistence", not persistPrompt())
    Symbol: SessionStore::persist (Class::method or function name, for the write-up's references)
    File: src/sessions/persist.ts
    Responsibility: what it does + why it exists (1–2 sentences)
    Connections: what it reads / who calls it / what it produces
    Anchor code: 1–5 lines of the most telling real code
  ```

  The main context only orchestrates and synthesizes; if a subagent's report has
  gaps, drop that node instead of reading files on its behalf — unless the node is
  the backbone of the answer.
- Record the traps a newcomer would hit: hidden coupling, surprising ownership,
  legacy detours.

## Step 3 — Build the mental model

An explanation is built from two complementary views. The **static view** says what
the system is made of and how its units relate, independent of any single execution.
The **dynamic view** says how one concrete scenario executes to its logical
endpoint. Name the participating boundaries with enough static context first, then
trace the dynamic flow; focus on the view that was asked for, without expanding into
every part of the codebase.

### Static view

- **Layers.** A layer is a responsibility boundary at one level of abstraction — not
  a directory, not a call-stack frame. For each relevant layer, state: what
  responsibility it owns; which interfaces or entry points it exposes; which
  lower-level capabilities it depends on; what state or resources it owns; what
  boundary control crosses on the way in and out.
- **Module scope.** A module is a unit relative to the question's scope — possibly a
  whole process, a subsystem, a cohesive component, or the operation behind one
  endpoint. Declare the chosen scope first, then explain; describe what it provides,
  its inputs and outputs, its callers and dependencies, the state it owns.
- **Relationship kinds.** Distinguish structural containment, source-level
  dependency, runtime calls, shared-data coupling, and deployment boundaries —
  label every relationship with its specific kind.

### Dynamic view

Follow the scenario through calls, data changes, triggers, and state transitions
until the **logical endpoint** — which may fall inside the initiating request or
after it has already returned.

- **Logically synchronous flow**: the initiating request returns only after the
  operation reaches its terminal state from the caller's perspective — a success
  response means done, an error means definitively failed. Explain as one end-to-end
  path: entry, participating layers and modules, key calls and state changes,
  completion condition, final response.
- **Logically asynchronous (detached) flow**: the initiating request accepts or
  registers work and returns early — the response means only "accepted", not "done".
  Cut the explanation at the async boundary and state: where the request returns and
  what that response guarantees; what work and state were persisted before return;
  what triggers each continuation (scheduler, queue, event, callback, worker,
  reconciliation loop); how a continuation restores context and advances state; what
  condition defines logical completion; how the caller observes intermediate and
  final results.

Always distinguish request completion from the operation's logical completion.

Change questions: model before and after separately, then explain the delta.

### Focus decides which details surface

Every detail must serve the question. The cut hinges on one test: **is it this
code's own logic**.

- **Key facts — keep**: who executes, who owns state, where boundaries are crossed,
  where it waits.
- **Common ground — declare up front, reference compressed**: when a flow passes
  through mechanisms well known to both the LLM and the reader, state the assumption
  in one opening sentence — "the following assumes the reader knows the Raft
  protocol"; afterwards the body can write compressed statements like "the Leader
  syncs the raft log to Followers" or "only the Leader executes, then syncs results
  to Followers". The mechanism stays in the assumption; the main line carries only
  this code's own logic.

(The Flow example in Step 4 is cut exactly this way.)

## Step 4 — Compose the answer

The write-up is a complete answer made of diagrams plus interpretation. Every
explanation follows the same skeleton:

```text
1. One-line conclusion — one paragraph answering the original question
2. Common-ground note  — optional: when the flow leans on a well-known mechanism,
   declare the assumption up front and reference it in compressed form
3. Main view           — one diagram/tree/branch narrative carrying the main explanation
4. Interpretation      — step-by-step or layer-by-layer text hugging the main view,
   two or three sentences each
5. Supplementary view  — only when another angle is needed to make it clear, at most one
6. References          — key symbols (Class::method) with their files, so the reader
   can jump into the code
7. Uncertainty flags   — inferred edges and disagreements with docs, marked explicitly
```

The six examples below are the **default look** of each shape's write-up. Their
contexts are fictional, demonstrating only structure and density; their symbols and
file names are illustrative too.

### Composing a Flow

> **One-line conclusion**: Prewrite is routed by the RPC layer to the Raft Leader;
> the Leader checks for lock conflicts, then syncs the raft log, and every replica
> replays it into its local engine; the Leader replies as soon as its own replay
> completes, without waiting for the others.
>
> **Common ground**: the following assumes the reader knows the Raft protocol.
>
> ```mermaid
> sequenceDiagram
>     participant Client
>     participant RPC as RPC ingress
>     participant Leader as Raft Leader
>     participant Follower as Raft Follower
>     Client->>RPC: Prewrite
>     RPC->>Leader: route by Region
>     Leader->>Leader: check lock conflicts
>     Leader->>Follower: sync raft log
>     Note over Leader,Follower: all replicas replay into local engines
>     Leader-->>Client: success
> ```
>
> **Steps**:
> 1. **Entry**: `KvService::prewrite` routes by Region to the Leader.
> 2. **Leader check**: checks lock conflicts (before `Peer::propose`).
> 3. **Sync & replay**: the Leader syncs the raft log; all replicas replay into
>    their local engines.
> 4. **Response**: the Leader returns success once its own replay completes.
>
> **References**: `KvService::prewrite` (entry, server/service/kv.rs) · `Peer::propose` (check, raftstore/store/peer.rs) · `ApplyFsm::handle_apply` (replay, raftstore/store/fsm/apply.rs)

### Composing a Structure

> **One-line conclusion**: the write path has four layers — the RPC ingress layer
> validates and routes; the raftstore consensus layer owns the Leader check and log
> replication; the state-machine layer replays committed logs on **every node**; the
> storage engine only persists locally. The consensus layer is the only one that
> initiates cross-machine communication.
>
> ```mermaid
> graph TD
>     RPC[RPC ingress] -->|in-process call| Raft[raftstore consensus]
>     Raft -->|network replication, cross-machine| Peer[peer raftstore]
>     Raft -->|async dispatch after commit| FSM[local state machine]
>     Peer -->|replays the same log| PeerFSM[peer state machine]
>     FSM -->|write batch| Engine[storage engine]
>     PeerFSM -->|write batch| Engine
> ```
>
> | Layer | Responsibility | Exposes | Depends on | Owns state |
> |---|---|---|---|---|
> | RPC ingress | validation, routing by Region | `KvService` API | raftstore | stateless |
> | raftstore consensus | Leader check, propose, replication | `Peer::propose`, Region message channel | state machine | raft log, Leader identity |
> | Raft state machine | replay committed logs, produce write batches | completion callback of `ApplyFsm` | engine | replay cursor |
> | storage engine | local KV persistence | `Engine::write` write-batch API | none | WAL/SST |
>
> **Note**: the three edge kinds differ — `RPC → raftstore` is an in-process call;
> `raftstore → peer` is network replication (across machines); `→ state machine` is
> asynchronous dispatch after commit, not a synchronous call. One state machine runs
> per node; splitting it into two diagram nodes expresses exactly that.
>
> **References**: `KvService` (src/server/) · `Peer` and `ApplyFsm` (components/raftstore/) · `engine_rocks` (engine implementation)

### Composing a Logic

> **One-line conclusion**: the essence of this function is a "check cache → write
> back → invalidate" decision tree; the difficulty lives in its two early returns.
>
> ```text
> on(save)
>   if content unchanged
>     return cached result       # early return 1: no write path
>   write new content
>   if write failed
>     log and return error       # early return 2: cache untouched
>   invalidate old cache
>   return new result
> ```
>
> **Decision points**: the two early returns protect two invariants — "a read-only
> path produces no side effects" and "a failed write never touches the cache";
> invalidation must happen after a successful write — the order is not
> interchangeable (see the invalidation call in `SessionStore::save`).
>
> **References**: `SessionStore::save` (sessions/store.ts)

### Composing a Change

> **One-line conclusion**: this PR changes save from an unconditional write to a
> cache hit when content is unchanged, and adds an event subscription after session
> navigation. Two behavior changes; the risk point is the cache-invalidation order.
>
> ```diff
>  on(save)
> +  if content unchanged
> +    return cached result
>    write new content
> +  invalidate old cache
> ```
>
> | Scenario | Before | After |
> |---|---|---|
> | Repeated save | full write every time | cache hit |
> | Write failure | cache invalidated as before | cache kept (see decision point 2 above) |
>
> **References**: `SessionStore::save` (main change, sessions/store.ts) · `SessionPage`'s event subscription (routes/session.tsx)

### Composing a Concept

> **One-line conclusion**: "Session" in this codebase = one full interaction cycle
> between user and agent, owned by the `sessions/` module, spanning the command and
> transport layers.
>
> ```text
> src/
> ├── commands/   # parses user actions, triggers session ops
> ├── sessions/   # owns session state and lifecycle ← the concept's home
> └── transport/  # syncs session changes to the server
> ```
>
> **One example flow** (how the concept shows up at runtime): create session →
> persist prompt → start agent → navigate to session page. Expand with
> `/show-me session creation flow`.
>
> **References**: `SessionStore` (definition, sessions/store.ts) · `createSession` command (main trigger, commands/create.ts)

### Composing a Data Model

> **One-line conclusion**: three core entities — User, Team, Session. Session is the
> only entity attached to both User and Team; all messages cluster around Session
> via foreign key.
>
> ```mermaid
> erDiagram
>     USER ||--o{ SESSION : "starts"
>     TEAM ||--o{ SESSION : "belongs to"
>     SESSION ||--o{ MESSAGE : "contains"
>     USER {
>         string id PK
>         string email UK
>     }
>     SESSION {
>         string id PK
>         string user_id FK
>         string team_id FK
>     }
> ```
>
> | Entity | Defined at | Key fields | Referenced by |
> |---|---|---|---|
> | User | `users` table (db/schema.ts) | id, email | Session.user_id |
> | Session | `sessions` table (db/schema.ts) | user_id, team_id | Message.session_id |
>
> **References**: `db/schema.ts` · `db/migrations/`

### Rendering cheat sheet

Pick the rendering by shape:

- **Branch narrative** — logic or algorithms: list branches, early returns, and
  state transitions by indentation, one plain-language line each. Keep wording at
  the plain-language level — field names, API calls, and concrete expressions go
  into the referenced symbols; the reader is reading an explanation, not code.
- **Call tree** — control flow within a single process (indented tree).
- **Mermaid sequence / flow diagram** — interactions or data flow across boundaries;
  every edge carries a verb label saying only "what this step does"; protocol and
  method names go to the referenced symbols.
- **Annotated shallow file tree** — file responsibilities or the blast radius of a
  change.
- **Mermaid layered / component diagram** — static structure at the chosen scope.
- **Mermaid erDiagram** — data models, table relations.
- **Diff shape** — the point is "what changed" and a surrounding shape already
  exists; works for call trees, file trees, branch narratives, state machines.
- **Full block** — most of the shape is newly written, or the user needs a copyable
  target shape.

## Quality checklist

Check each item before delivering; rework whatever fails. Consider dispatching a
suitable subagent for the check — input is the draft plus the code, output is a
list of failing items, keeping the main context free of line-by-line verification:

- The first paragraph is the one-line conclusion, zero pleasantries
- The question shape is decided; the rendering matches its default (or the deviation
  is justified)
- Each view has ≤7 nodes; overflow was split, not crammed
- Every label points at code actually read; inferred edges are marked with dashed
  lines or `?`
- Every edge has a verb label ("triggers" / "reads" / "writes")
- Detail serves the focus: key facts — who executes, who owns state, where it
  waits — are kept; well-known mechanisms are declared as common ground and
  referenced in compressed form
- Branch narratives are entirely plain language
- Async flows mark: where the request returns, what was persisted before return,
  continuation triggers, the logical completion condition
- References use stable symbols + their file (`Class::method`, file); line numbers
  appear only when the user asks; source snippets are quoted only when truly
  necessary
- README/comment claims have been checked against the implementation; discrepancies
  are noted
- Each view sits next to the text it supports
- The view set is minimal; every diagram serves the question
