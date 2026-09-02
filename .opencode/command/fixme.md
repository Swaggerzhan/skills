Search the current project's code for the markers `FIXME(ai)` and
`ASK(ai)`. Every marker carries a description written by the user. Read it
and its surrounding context.

For each `FIXME(ai)` marker:
- If the request is clear and unambiguous, implement the change directly.
- If anything is unclear, do not touch it; raise it as an open question.

For each `ASK(ai)` marker, discuss it with the user:
- Investigate the code and give your conclusion.
- Do not modify any code before the discussion is finished.
- If the conclusion requires a change, wait for the user's command, then
  implement it.

Report concisely: changes made (per FIXME), open questions (unclear FIXMEs),
conclusions (per ASK), each with its file location.

Once the user is satisfied with a marker's result, remove the marker comment.
