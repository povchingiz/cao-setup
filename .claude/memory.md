# Project Memory & Architecture Decisions

Append-only log of environment quirks, third-party breaking changes, and
non-obvious bugs. One line per entry, newest at the bottom of its section.

## Known Quirks & Bugs

- [2026-09-23] macOS has no `timeout` coreutil by default — use `gtimeout` (coreutils) or a background+kill pattern in shell scripts.
- [2026-09-23] `ruff check .` reports 196 pre-existing errors in this repo. Verification gate treats ruff as advisory, pytest as blocking. See `.claude/verify.sh`.
- [2026-09-23] `setup/2_configure/cao.config.local.toml` overrides the tracked `cao.config.toml` and is gitignored. Editing only the tracked file changes nothing at runtime - edit both, then run `./setup/3_apply/apply.sh`.
- [2026-09-23] `cao update` / reinstall rewrites site-packages and erases the `wait_for_shell` patch; launches then time out after 60s. `cao-run` self-repairs via `run/cao-patch`; `cao-doctor` D8 checks it.
- [2026-09-23] Worker panes inherit the *daemon's* environment, not the invoking shell's. A hand-started `cao-server` has no `LOCAL_API_KEY`, so every opencode worker fails auth with no clear cause. Start via `cao-run`.
- [2026-09-23] Aliases in `[workers.*]` render into the supervisor's routing table as prose. Two workers sharing one alias makes routing nondeterministic - `render_config.validate()` now rejects it.

## Architecture Decisions

- [2026-09-23] Context stack: lean-ctx for read/shell compression, symdex for AST navigation, context7 for third-party library docs. Test and typecheck output is never compressed — see `.claude/rules/code-integrity.md`.
- [2026-09-23] Agent rules are modular files under `.claude/rules/`, not one monolithic prompt. Caveman-style prompt injection was removed; it degrades reasoning and diff quality.
