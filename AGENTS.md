# AGENTS.md

## Working principles

- Keep code, comments, and commit messages brief.
- Assume maintainers and readers know the project's domain. Use clear names;
  comment only non-obvious behavior.
- Keep public APIs minimal. Avoid global mutable state.
- Search existing helpers and prior solutions before adding new abstractions.

## Tests and validation

- Prefer the project's end-to-end or integration tests. Use unit tests for
  isolated utilities.
- Use the project's established assertion style, not ad hoc failure checks.
- Name tests for behavior. Record issue references separately from test names.
- Preserve required attribution when adapting tests or other contributed work.
- Remove temporary debug output before completion; use project-native
  diagnostics only when needed during investigation.
- Run only documented, project-native validation commands. Do not invent
  commands or claim unverified results.

## Ownership and safety

- `SPEC.md` is contract truth and has one write owner: `lithon-specificator`. Do
  not edit it without that owner's authorization.
- Treat secrets, protected inputs, and ignored local surfaces as read-protected.
  Do not expose, move, derive, or edit them without explicit authorization.
- Read `SECURITY.md` before security-sensitive work, when present.
- Keep changes within the requested edit surface. Unknown behavior remains
  `unknown` until verified.
