# Project Memory & Architecture Decisions

Append-only log of environment quirks, third-party breaking changes, and
non-obvious bugs. One line per entry, newest at the bottom of its section.

## Known Quirks & Bugs

- [2026-09-23] macOS has no `timeout` coreutil by default — use `gtimeout` (coreutils) or a background+kill pattern in shell scripts.
- [2026-09-23] `ruff check .` reports 196 pre-existing errors in this repo. Verification gate treats ruff as advisory, pytest as blocking. See `.claude/verify.sh`.

## Architecture Decisions

- [2026-09-23] Context stack: lean-ctx for read/shell compression, symdex for AST navigation, context7 for third-party library docs. Test and typecheck output is never compressed — see `.claude/rules/code-integrity.md`.
- [2026-09-23] Agent rules are modular files under `.claude/rules/`, not one monolithic prompt. Caveman-style prompt injection was removed; it degrades reasoning and diff quality.
