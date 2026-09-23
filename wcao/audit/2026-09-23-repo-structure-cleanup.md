# Audit — repo structure cleanup

*2026-09-23. Scope: `~/cao-setup` / `~/wcao`. Audited first, then F1 and F2 were
fixed - see Outcome at the end.*

## Headline: there is no `cao-setup` folder

```
/Users/yerta/cao-setup -> /Users/yerta/wcao   (symlink, created 2026-09-22)
```

Both paths resolve to one working tree, one `.git`, one HEAD. There is no
second checkout, no duplicated content, and nothing to reconcile between them.

This corrects the "dual-checkout layout" framing in
`wcao/plans/2026-09-23-robust-setup-process.md` (§Out of scope, §Still open) —
that layout never existed. What exists is a **stale name** kept alive by a
symlink.

## Size

3.8M total, of which `.git` is 1.9M — i.e. half the repo is history, and the
working tree is ~1.9M across 97 tracked files. **This repo is not bloated.**
No compression, pruning, or large-file surgery is warranted. Everything below
is about structure and naming.

| Path | Size | Tracked | Note |
|---|---|---|---|
| `.git` | 1.9M | — | normal for this history |
| `run/` | 608K | yes | 13 executables + 11 modules |
| `tests/` | 368K | yes | 56 tests, all passing |
| `wcao/` | 292K | yes | plans/audit/design + runtime sqlite (ignored) |
| `.venv`, `.ruff_cache`, `.pytest_cache`, `.generated` | 132K | no | correctly ignored |

`.gitignore` covers every build artifact present, and **no artifact is
tracked** (verified: no `__pycache__`, `.pyc`, venv, cache, sqlite, or
`.DS_Store` in the index). Nothing to clean here.

---

## F1 — `presentation.html` is a byte-identical copy of `index.html` — [x] `0601187`

**Severity: medium.** The only finding with real ongoing cost.

- 122,247 bytes each; `cmp` reports them identical.
- Both tracked. `git log --follow` shows **every commit touches both** —
  `641a533`, `bc39de1`, `606f9e2`, `e510978`, `5f3f96b`. Someone is hand-
  syncing a 122K file across two paths.
- **Zero references to `presentation.html`** anywhere in the repo.
  (`run/cao_config_server.py:504` matches `index.html`, but that is its own
  HTTP route — unrelated.)
- `.nojekyll` is present, so GitHub Pages serves `index.html`.

The risk is not disk: it is that two copies edited by hand will eventually
diverge, and the deck published to Pages will silently disagree with the one
in the repo.

**Recommendation:** delete `presentation.html`, keep `index.html`. It is
recoverable from history. A symlink is not a substitute — GitHub Pages does
not follow repo symlinks, so that URL would break regardless.

## F2 — the `cao-setup` name is stale in 6 tracked files — [x] `bf82d2f`

**Severity: low.** Nothing is broken today, because the symlink resolves.

| File | What |
|---|---|
| `pyproject.toml:2` | `name = "cao-setup"` |
| `uv.lock:6` | `name = "cao-setup"` (regenerates from pyproject) |
| `WINDOWS.md` | 6 references instructing a clone to `~/cao-setup` |
| `1_install/bootstrap.ps1` | 6 references; clones into `~/cao-setup` |
| `1_install/bootstrap.sh:171` | cosmetic string in a PATH comment |
| `.venv/pyvenv.cfg` | `prompt = cao-setup` (ignored, regenerates) |

The two installers matter: a new Windows/WSL user is told to clone into
`~/cao-setup`, which is the *old* name. They end up with a real directory at
the path that is a symlink here — divergent setups across machines, which is
the class of problem the cross-machine install already hit.

Historical references in `wcao/audit/*` and `wcao/design/*` should be left
alone — they are dated records of what the project was called then.

**Recommendation:** rename the package to `wcao`, update the two installers
and `WINDOWS.md`, keep the `~/cao-setup` symlink so existing muscle memory and
any local scripts keep working.

## F3 — `run/` mixes executables and modules — leave it alone — [x] no action, by design

**Severity: none. Recommend no change.**

`run/` holds 13 executables (`cao-*`) and 11 importable modules (`cao_*.py`).
Cosmetically this looks like it wants a `run/lib/` split. It does not:

- `tests/` already imports `run/` **as a package** — `from run.cao_auto
  import AutonomousRunner` in `test_audit_gate.py`, and the same shape in
  `test_telegram.py`, `test_tamper.py`, `test_fallback.py`,
  `test_token_master.py`.
- 10 files perform `sys.path` insertion against three different anchors
  (`REPO`, `RUN_DIR`, `HERE`).
- `pyproject.toml` sets `pythonpath = ["."]` for pytest.
- `1_install/bootstrap.sh` symlinks each executable by name into
  `~/.local/bin`.

A move would touch all of that to gain nothing functional. The dash/underscore
convention already separates the two kinds of file unambiguously. **Leave it.**

---

## Recommended order

1. **F1** — delete `presentation.html`. Self-contained, removes a real
   sync burden.
2. **F2** — rename to `wcao` in the package metadata and the two installers.
   Touches the install path, so it deserves its own commit and a
   `bootstrap.sh --help` smoke check.
3. **F3** — no action.

Not recommended: any `run/` reorganization, any `.git` surgery, any change to
`.gitignore` (already complete).

## Verification for whatever lands

`uv run --with pytest pytest tests/` must stay at **56 passed**, and
`run/cao-doctor` must stay at 0 failed. Full gate: `.claude/verify.sh`.

---

## Outcome (2026-09-23)

F1 and F2 landed; F3 was deliberately left alone.

| Commit | What |
|---|---|
| `0601187` | Deleted `presentation.html` (122K duplicate). |
| `bf82d2f` | Renamed the package to `wcao`; fixed the install path in both installers and `WINDOWS.md`. |

**Found while fixing, not in the audit:** `WINDOWS.md`'s quickstart ended with
`./bootstrap.sh`, which does not exist at the repo root - the script is
`./1_install/bootstrap.sh`. A Windows user following that file verbatim failed
at the final step. Fixed in `bf82d2f`.

**Backward compatibility:** `bootstrap.ps1` still accepts an existing
`~/cao-setup` in both its clone guard and its WSL handoff, so a machine that
already cloned under the old name keeps working. The local
`~/cao-setup -> ~/wcao` symlink is untouched.

Verified: 56 tests pass, `cao-doctor` 0 failed, the bash fragments emitted by
the edited PowerShell parse cleanly, and the `~/wcao` -> `~/cao-setup`
fallback resolves when the new path is absent.
