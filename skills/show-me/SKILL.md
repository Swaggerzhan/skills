---
name: show-me
description: Explain this codebase visually — flow, structure, change, algorithm, concept, or data model.
disable-model-invocation: true
---

# Show Me

Invoked as `/show-me <description>`. Produce a **visual-first** explanation: a
minimal set of sketches, each next to the short text it supports. Skip
pleasantries — the sketches carry the explanation; the text only frames them.

Empty description → ask one short question. Ambiguous → state your reading in
one sentence and proceed.

## System views

Draw every view with the shared **system-views** skill — load it first and
apply its vocabulary, renderings, and rules. They are not restated here.

## Pick the shape

| Shape | Question sounds like | Default rendering |
|---|---|---|
| Flow | "how does X work", "what happens when…" | call tree or mermaid diagram — whichever fits the flow |
| Architecture | "architecture of X" | node-and-channel graph |
| Code organization | "how is X organized", "what modules exist" | mermaid component diagram or annotated file tree |
| Logic | "explain this algorithm/function" | branch narrative |
| Change | "what does this PR do", "before vs after" | diff of the existing shape |
| Concept | "what is X in this codebase" | small map + one example flow |
| Data model | "how is the data stored", "schema/layout of X" | erDiagram for a database schema; plain-text box layout for an on-disk format or in-memory structure |

Flow vs. logic: if answering requires naming a **second ownership boundary**
(another module, process, or async continuation), it's a flow — render the
participants and boundary crossings. If the difficulty is one unit's internal
branches, it's logic — render the decisions.

Narrow question → explore and explain in one pass. Wide question (a subsystem,
the whole repo) → dispatch 2–4 exploration subagents in parallel, one angle
each; ask for nodes with responsibilities and connections, not code dumps.

## Explore

Read real code: judgments rest only on implementations actually read; file
names and READMEs are locating clues. Start from landmarks — manifests, entry
points, route/handler registrations, symbols named in the request. Follow the
thread from trigger to outcome until you can state every step without hedging.
Record the traps a newcomer would hit: hidden coupling, surprising
ownership. Check README and comment claims against the implementation;
note discrepancies.

## Terms

Open the document with a **Terms** section, one line per term — but only for
names this project coined or repurposed: its own components, libraries,
internal mechanisms, and acronyms a reader cannot resolve outside this repo
(e.g. Mooncake's `EP`, `PG`, `tent`). A term qualifies only if it shows up in
your views and the main line is unreadable without it.

Never gloss industry terms — Raft, RDMA, TCP, CRDT, C++ — however obscure;
the reader can look those up. Test: "searching this term alone lands on the
right meaning" → leave it out. When in doubt, leave it out.

Ground every entry in the repo: expansion and role come from code, manifests,
or docs you actually read. Never guess an acronym's expansion; if the repo
never expands it, give the role only. Omit the section entirely when nothing
qualifies.

## Compose

Skeleton, in order: Terms (only if any qualify) → main view → short
interpretation hugging the view → references (`Class::method` + file) →
uncertainty flags if any. At most one supplementary view, only when another angle is needed.

For wide questions with several sections: structure before behavior —
architecture, nodes, and data structures first, then the flows over them;
within architecture, global before local. Simple subjects don't need this
rigor — adapt the order to the question.

Keep only details that serve the question: who executes, who owns state, where
boundaries are crossed, where it waits. When the flow leans on a well-known
mechanism (e.g. Raft), declare it in one opening sentence and then reference it
compressed — the main line carries only this code's own logic.

