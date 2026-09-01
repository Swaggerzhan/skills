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
- When describing code, prefer stable symbols such as `Class::method` over
  file-and-line references unless the user explicitly requests line references.
- When the cost of asking a follow-up question is lower than the cost of a mistake requiring rework, ask. Otherwise, offer the best judgment and clearly note any assumptions.

## Documentation and Design Artifacts

- Include only decision-relevant content.
- For explicitly rejected or removed content, update the active code and design
  accordingly. Do not leave comments or placeholders merely to preserve it;
  retain concise rationale only as an intentional decision record or when
  required by project conventions.
