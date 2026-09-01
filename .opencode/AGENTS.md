# Project Rules

This repository is used to create and produce Skills.

- When creating or modifying Skills, follow the specifications and examples in the `agentskills/` directory.
- All Skills created in this repository must be written in English only. Chinese content is not allowed.
- All Skills must be created under the current project's `skills/` directory.

## Output Specifications

If removing a section does not affect decision-making, do not include it.

- Present conclusions or solutions directly, without introductory remarks.
- Omit obvious context and known information.
- Provide examples only when they are essential for understanding key logic.
- When the cost of asking a follow-up question is lower than the cost of a mistake requiring rework, ask. Otherwise, offer the best judgment and clearly note any assumptions.

## Documentation and Design Artifacts

- A concept judged meaningless, invalid, unnecessary, or removable must be treated as non-instantiated absence, not as negated content.
- Apply semantic de-anchoring and hard deletion.
- Critique is control metadata, not document content.
- Do not instantiate, restate, negate, prohibit, warn about, justify, contrast, or otherwise reintroduce the rejected concept.
- Unless an explicit replacement is requested, generate no replacement content.
