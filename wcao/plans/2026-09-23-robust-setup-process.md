# Plan — Robust setup process

*Created 2026-09-23. Source: `fix/session-launch-timeout` + the cross-machine install experience.*

## Goal

Make a fresh install on an unfamiliar machine either **work**, or **fail with a message that names the real cause**. Today it can do neither: `cao-doctor` reported 15 passed / 1 warning / 0 failed while every supervisor launch was failing.

## What went wrong (the lessons being encoded)

| # | Lesson | Encoded as |
|---|---|---|
| L1 | A 60s server-side shell-init timeout surfaced as a 30s *client* "failed to connect", then a bogus `400`. Two symptoms, one cause. | Phase 1 |
| L2 | Doctor validated **presence** (binaries, endpoint) but never **function** (can a session actually launch?). It passed while nothing worked. | Phase 3 |
| L3 | `.env` discovery was a hardcoded 3-entry list of someone's home dirs. Broke on any other machine/checkout. | Phase 2 |
| L4 | `opencode_cli` fails auth silently when `LOCAL_API_KEY` is absent from the daemon's env — no error names the key. | Phase 3 (D5) |
| L5 | Patches to `site-packages` are erased by `cao update`, silently reintroducing L1. | Phase 4 |
| L6 | Two workers shared the alias `"bulk"`, making engine routing nondeterministic — so "which engine is better" is unanswerable. | Phase 5 |
| L7 | `apply.sh` had not run since the config changed: the live supervisor prompt lists 4 workers and names `opencode_worker`, which no longer exists. Config and runtime drifted with no detector. | Phase 3 (D6) |

## Phases

Ordered by dependency. Each is independently shippable and independently revertable.

---

### Phase 1 — Take the launch fix *(unblocks everything)* — [x] `7efc80b`

Cherry-pick `e649602` from `fix/session-launch-timeout`.

- `1_install/patch_shell_wait.py` (new) — `wait_for_shell` falls back to `backend.get_history()` when the StatusMonitor buffer is still blank. Reuses the exact call the herdr path and the pipe-liveness watchdog already make; not a new mechanism.
- `1_install/bootstrap.sh` — run the patch next to `patch_pyte.py`, `|| warn` (never fail the install).
- `run/cao-run` — reap the half-created session before the fallback retry, so a client-side timeout stops cascading into a bogus `400`.

**Verified already:** the patch's `OLD` string matches this machine's installed `terminal.py` byte-for-byte; `_resolve_window` (line 87) and `backend` are both in scope. Applies cleanly.

**Exit criteria:** 6 back-to-back `POST /sessions` all reach `idle`; `pytest tests/` still 56 passed.

---

### Phase 2 — Env/path resolution *(L3)* — [x] `a8bd195`

Replace the hardcoded `$HOME/wcao` · `$HOME/cao-setup` lists in `run/cao-run:74` and `run/cao-doctor:30` with a single shared resolver.

- Add `run/_cao_common.sh` — sourced by `cao-run`, `cao-doctor`, `cao-stop`.
- Resolution order: `$CAO_ENV_FILE` (explicit override) → `$REPO/.env` (resolved through symlinks from `BASH_SOURCE`) → `$PWD/.env` → `$HOME/.config/cao/cao.env`.
- Keep loading until `LOCAL_API_KEY` is actually set, not merely until the first file exists — the branch already fixed this in doctor; generalize it.
- Report *which* file supplied the key (never the value).

This takes the branch's fix and finishes it: the branch grew the list to five entries, this removes the assumption that the repo lives at a known path.

**Exit criteria:** works from a checkout at an arbitrary path with no `$HOME/wcao`; `shellcheck` clean.

---

### Phase 3 — Doctor: check function, not just presence *(L2, L4, L7)* — [x] `33352c4`

The highest-value phase. Four new checks:

- **D5 — Launch smoke test** *(the check that would have caught the incident)*
  `POST /sessions` with a throwaway name, assert it reaches `idle`, then tear it down. Gate behind `--deep` so the default stays fast.
- **D6 — Config/runtime drift**
  Re-render config to a temp dir and diff against the live store. Warn when they differ (catches L7 today).
- **D7 — Daemon env**
  Assert the *running daemon* can see `LOCAL_API_KEY`, not just the shell. Names L4 directly, which currently fails silently.
- **D8 — Patch integrity**
  Assert the `# wcao:` markers are present in installed `site-packages`. Catches L5 after any `cao update`.

Also: make `cao-doctor` exit non-zero on the warnings that actually block launches, instead of summarizing them into a green "Ready."

**Exit criteria:** deliberately break each of L1/L4/L7 and confirm doctor names the right cause each time.

---

### Phase 4 — Patch durability *(L5)* — [x] `93eb8d2`

`patch_shell_wait.py` and `patch_pyte.py` are erased by `cao update` / reinstall.

- Add `run/cao-patch` — reapplies all `site-packages` patches idempotently.
- Call it from `cao-run` startup (cheap marker check; reapply only when missing).
- Note the constraint in `AGENTS.md` troubleshooting.

Ordered after Phase 3 so D8 exists to verify it.

---

### Phase 5 — Separate hermes and opencode *(L6)* — [x] `61cb415`

Restore distinct routing so the engines can actually be compared.

| Worker | Provider | Aliases |
|---|---|---|
| `coder_worker` | `hermes_cli` | `coder`, `code`, `hermes` |
| `opencode_worker` | `opencode_cli` | `opencode`, `bulk`, `cheap` |

- No alias appears on two workers. Add a duplicate-alias assertion to `render_config.py` so this cannot regress silently.
- Rename `hermes_worker` → `opencode_worker` so the name matches its provider (the current cross-wiring is what made this confusing).
- Run `apply.sh`, which also clears the L7 drift.

To compare the engines: route the same task class to each by explicit alias, and read cost/latency from `tasks.json` + `cao-limits`. Sharing an alias gives a coin flip with no record; distinct aliases give data.

---

### Phase 6 — Fold the audit in — [x]

- Move `wcao/audit/2026-09-23-session-launch-timeout.md` onto master (commit `76c7404`).
- File audit open items **#1** (FIFO reader stall not root-caused) and **#6** (upstream cold-start rescue guards on `ever_delivered`, unreachable for this failure shape) upstream against CAO.
- Log the durable quirks in `.claude/memory.md`.

---

## Sequencing

```
Phase 1 ──┬── Phase 2 ── Phase 3 ── Phase 4
          └── Phase 5        │
                   Phase 6 ──┘
```

Phase 1 first — nothing is testable until launches succeed. Phases 2 and 5 are independent. Phase 3 depends on 2 (shared resolver) and wants 5 done (so D6 drift-checks a correct config). Phase 4 needs D8 from Phase 3.

## Out of scope

- Root-causing the FIFO reader stall — upstream CAO; the patch bypasses the gate, it does not fix the pipeline.
- Restructuring the `wcao/` ↔ `cao-setup/` layout. Phase 2 makes path resolution independent of it; the layout decision is separate. *(Later finding: `~/cao-setup` is a symlink to `~/wcao` — there is no dual checkout. See `wcao/audit/2026-09-23-repo-structure-cleanup.md`.)*

## Verification

Every phase: `uv run --with pytest pytest tests/` stays at **56 passed**. Full gate is `.claude/verify.sh`.

Whole-plan acceptance: a clean checkout on a machine with no `$HOME/wcao`, running `bootstrap.sh` → `cao-doctor --deep` → `cao-run`, reaches a live supervisor — or fails with a message naming the actual cause.

---

## Outcome (2026-09-23)

All six phases landed. `cao-doctor` goes from 15 passed / 1 warning / 0 failed
(while everything was broken) to 17 passed / 4 warnings / 0 failed with checks
that would actually have caught the incident. 56 tests pass throughout.

### Where this diverged from the plan

- **No worker rename.** The plan proposed `hermes_worker` -> `opencode_worker`.
  Master already wired `coder_worker` -> opencode_cli and `hermes_worker` ->
  hermes_cli (the *branch* is what cross-wired them), so the rename was both
  backwards and a wide change - `coder_worker` is referenced across 6 test
  files, docs, `tasks.json` and an SVG. Dropped it; distinct aliases plus the
  `validate()` guard achieve the actual goal.
- **Ruff stayed advisory.** 196 pre-existing errors would block every task.
- **D7 degrades on macOS.** It reads `/proc/<pid>/environ`, which does not
  exist there; it warns rather than claiming a pass it cannot verify. The real
  check runs on Linux.

### Found while implementing, not in the plan

- `patch_shell_wait.py` exited 0 when it could not apply, so the self-repair
  would silently no-op. Now exits 2.
- `cao.config.local.toml` overrides the tracked config and is gitignored -
  this is why the live routing table had drifted.

### Still open

- Audit items #1 (FIFO stall not root-caused) and #6 (upstream's cold-start
  rescue is unreachable for this failure shape) - both belong upstream.
- Items #4, #5, #7 - low severity, untouched.
- ~~The `wcao/` vs `cao-setup/` dual-checkout layout.~~ **Resolved, and the
  premise was wrong:** `~/cao-setup` is a symlink to `~/wcao`, not a second
  checkout - there was never anything to reconcile. The stale *name* was
  fixed in `bf82d2f`. See
  `wcao/audit/2026-09-23-repo-structure-cleanup.md`.
