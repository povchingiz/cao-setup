# cao-limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cao-limits` — a CLI tool + Python API that reports engine quota status from existing on-disk data (no active probing).

**Architecture:** Shared library (`cao_lib.py`) extracted from `cao-tokens`, a core module (`cao_limits.py`) with dataclasses + parsing, and a thin CLI entry point (`cao-limits`). `cao-tokens` is refactored to import shared helpers from `cao_lib.py`.

**Tech Stack:** Python 3.11+ (stdlib only — json, sqlite3, dataclasses, pathlib, glob, datetime)

**Spec:** `plans/cao-limits-design.md`

## Global Constraints

- Python 3.11+ (same as `cao-tokens` — needs `tomllib` for apply.sh, but limits itself doesn't use it)
- No external dependencies (stdlib only)
- No API calls / active probing — read-only from disk
- Follow `cao-tokens` patterns: shebang `#!/usr/bin/env python3`, same arg parsing style, same `hn()` formatting
- `cao-tokens` must keep working identically after the refactor (no behavior change)
- Symlink goes into `~/.local/bin/cao-limits` via bootstrap

---

### Task 1: Extract shared helpers into `cao_lib.py`

**Files:**
- Create: `run/cao_lib.py`
- Modify: `run/cao-tokens` (import from cao_lib instead of inline)

**Interfaces:**
- Produces: `cao_lib._q(db, sql)`, `cao_lib._iter_claude_files(cutoff)`, `cao_lib._file_is_cao(path)`, `cao_lib.hn(n)`, `cao_lib.cutoff_ts(since)`, `cao_lib.HOME`, `cao_lib.CAO_MARKERS`

- [ ] **Step 1: Create `run/cao_lib.py`** with the shared helpers extracted verbatim from `cao-tokens`

```python
"""cao_lib — shared helpers for cao-tokens, cao-limits, and future tools.

Extracted from cao-tokens to avoid duplication. Every function here was
battle-tested in cao-tokens first; this module just gives them a shared home.
"""
import json
import os
import sqlite3
import sys
import time
from glob import glob
from pathlib import Path

HOME = Path.home()

# Markers that identify a claude session cao actually drove.
CAO_MARKERS = ("cao-mcp-server", "cao_", '"assign"')


def cutoff_ts(since):
    """Convert a --since string like '7d' into a Unix timestamp cutoff."""
    if not since:
        return 0.0
    n, unit = float(since[:-1]), since[-1]
    mult = {"h": 3600, "d": 86400, "w": 604800}.get(unit)
    if not mult:
        sys.exit(f"bad --since '{since}': use e.g. 24h, 7d, 2w")
    return time.time() - n * mult


def _iter_claude_files(cutoff):
    """Yield paths to Claude session .jsonl files, with mtime prefilter."""
    root = HOME / ".claude" / "projects"
    if not root.exists():
        return
    for f in glob(str(root / "**" / "*.jsonl"), recursive=True):
        if cutoff and os.path.getmtime(f) < cutoff:
            continue
        yield f


def _file_is_cao(path):
    """True if this claude session loaded cao's MCP server / used assign."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if any(m in line for m in CAO_MARKERS):
                    return True
    except OSError:
        return False
    return False


def _q(db, sql):
    """Run a read-only SQL query against a sqlite db; return rows or None."""
    if not Path(db).exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        out = con.execute(sql).fetchall()
        con.close()
        return out
    except sqlite3.Error:
        return None


def hn(n):
    """Human-compact number: 1234 -> 1.2k, 2_500_000 -> 2.5M, 0 -> 0."""
    n = int(n)
    if n == 0:
        return "0"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)
```

- [ ] **Step 2: Refactor `cao-tokens` to import from `cao_lib`**

At the top of `run/cao-tokens`, replace the inline definitions of `HOME`, `CAO_MARKERS`, `cutoff_ts`, `_iter_claude_files`, `_file_is_cao`, `_q`, `hn` with:

```python
from cao_lib import HOME, CAO_MARKERS, cutoff_ts, _iter_claude_files, _file_is_cao, _q, hn
```

Delete the now-duplicated function bodies from `cao-tokens`. Keep everything else (scrape functions, views, main) untouched.

- [ ] **Step 3: Verify `cao-tokens` still works identically**

Run: `python3 run/cao-tokens --json --since 7d`
Expected: Same JSON output as before the refactor (no functional change).

Run: `python3 run/cao-tokens`
Expected: Same heatmap + table as before.

- [ ] **Step 4: Commit**

```bash
git add run/cao_lib.py run/cao-tokens
git commit -m "refactor: extract shared helpers into cao_lib.py (prep for cao-limits)"
```

---

### Task 2: Build the `cao_limits` core module

**Files:**
- Create: `run/cao_limits.py`

**Interfaces:**
- Consumes: `cao_lib._iter_claude_files(cutoff)`, `cao_lib._file_is_cao(path)`, `cao_lib._q(db, sql)`, `cao_lib.HOME`, `cao_lib.hn(n)`
- Produces: `cao_limits.get_limits(cao_only=True) -> LimitReport`, `cao_limits.ClaudeLimits`, `cao_limits.WindowInfo`, `cao_limits.EngineSpend`

- [ ] **Step 1: Create `run/cao_limits.py`** with dataclasses and the `get_limits()` function

```python
"""cao_limits — engine quota status from on-disk data.

No API calls. Reads Claude rate-limit events from session logs and spend
totals for codex/opencode from their local SQLite databases.

CLI entry point: run/cao-limits (thin wrapper).
Python API: get_limits(cao_only=True) -> LimitReport
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Optional

from cao_lib import HOME, _file_is_cao, _iter_claude_files, _q


# ---- dataclasses -----------------------------------------------------------

@dataclass
class WindowInfo:
    """One rate-limit window (five_hour or seven_day)."""
    utilization: float  # 0.0 – 1.0
    resets_at: int       # Unix timestamp (seconds)
    status: str = ""     # "allowed" | "allowed_warning" | "rejected"

    @property
    def resets_at_iso(self) -> str:
        return datetime.fromtimestamp(self.resets_at, tz=timezone.utc).isoformat()

    @property
    def resets_in_seconds(self) -> int:
        return max(0, self.resets_at - int(time.time()))


@dataclass
class ClaudeLimits:
    """Claude rate-limit state from the most recent on-disk data."""
    five_hour: Optional[WindowInfo] = None
    seven_day: Optional[WindowInfo] = None
    blocked: bool = False                # True if latest signal was a 429 rejection
    blocked_window: str = ""             # "five_hour" if blocked
    blocked_resets_at: int = 0           # Unix ts of when rejection lifts
    stale_seconds: int = 0              # seconds since the data was written
    source_file: str = ""               # which file the data came from

    def is_near_limit(self) -> bool:
        """True if any window has utilization > 0.8 or status == allowed_warning."""
        for w in (self.five_hour, self.seven_day):
            if w and (w.utilization > 0.8 or w.status == "allowed_warning"):
                return True
        return self.blocked

    def is_blocked(self) -> bool:
        return self.blocked


@dataclass
class EngineSpend:
    """Spend totals for a non-Claude engine."""
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_combined: int = 0  # codex reports one number
    cost: float = 0.0          # opencode only


@dataclass
class LimitReport:
    """Complete limit/spend snapshot across all engines."""
    claude: Optional[ClaudeLimits] = None
    codex: Optional[EngineSpend] = None
    opencode: Optional[EngineSpend] = None
    agy: None = None  # always None — no local data
    timestamp: float = field(default_factory=time.time)


# ---- Claude rate-limit parsing ---------------------------------------------

def _scan_claude_rate_events(cao_only: bool) -> Optional[dict]:
    """Find the most recent rate_limit_event in tool-results/*.txt files.

    These are written by Claude when utilization crosses a threshold.
    Returns the parsed JSON dict of the most recent event, or None.
    """
    root = HOME / ".claude" / "projects"
    if not root.exists():
        return None

    best = None
    best_mtime = 0.0

    for session_dir in root.rglob("tool-results"):
        if not session_dir.is_dir():
            continue
        # CAO filter: check if the parent session's jsonl is a CAO session.
        parent = session_dir.parent
        if cao_only:
            jsonl_candidates = list(parent.parent.glob(f"{parent.name}.jsonl"))
            if jsonl_candidates and not _file_is_cao(str(jsonl_candidates[0])):
                continue

        for txt_file in session_dir.glob("*.txt"):
            try:
                mtime = os.path.getmtime(txt_file)
                if mtime <= best_mtime:
                    continue
                content = txt_file.read_text(encoding="utf-8", errors="ignore")
                data = json.loads(content)
                if data.get("type") == "rate_limit_event" and "rate_limit_info" in data:
                    best = data
                    best["_source_file"] = str(txt_file)
                    best["_mtime"] = mtime
                    best_mtime = mtime
            except (OSError, json.JSONDecodeError, KeyError):
                continue

    return best


def _scan_claude_rejections(cao_only: bool) -> Optional[dict]:
    """Find the most recent 429 quota rejection in Claude session jsonl files.

    Returns the parsed JSON dict of the most recent rejection, or None.
    """
    best = None
    best_ts = ""

    # Use a recent cutoff (7 days) to avoid scanning ancient history.
    cutoff = time.time() - 7 * 86400
    for f in _iter_claude_files(cutoff):
        if cao_only and not _file_is_cao(f):
            continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"quotaLimits"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    if o.get("error") != "rate_limit":
                        continue
                    ts = o.get("timestamp", "")
                    if ts > best_ts:
                        best = o
                        best_ts = ts
        except OSError:
            continue

    return best


def _parse_claude(cao_only: bool) -> Optional[ClaudeLimits]:
    """Build ClaudeLimits from the best available on-disk data."""
    event = _scan_claude_rate_events(cao_only)
    rejection = _scan_claude_rejections(cao_only)

    if not event and not rejection:
        return None

    limits = ClaudeLimits()

    # Parse the proactive rate_limit_event (has utilization + unifiedWindows).
    if event:
        info = event.get("rate_limit_info", {})
        windows = info.get("unifiedWindows", {})
        for key, attr in [("five_hour", "five_hour"), ("seven_day", "seven_day")]:
            w = windows.get(key)
            if w:
                setattr(limits, attr, WindowInfo(
                    utilization=w.get("utilization", 0.0),
                    resets_at=w.get("resetsAt", 0),
                    status=info.get("status", "") if info.get("rateLimitType") == key
                           else "",
                ))
        limits.stale_seconds = int(time.time() - event.get("_mtime", time.time()))
        limits.source_file = event.get("_source_file", "")

    # Parse the 429 rejection (stronger signal: you ARE blocked).
    if rejection:
        ql = rejection.get("quotaLimits", {})
        if ql.get("status") == "rejected":
            limits.blocked = True
            limits.blocked_window = ql.get("rateLimitType", "")
            limits.blocked_resets_at = ql.get("resetsAt", 0)
            # If rejection is MORE recent than the event, update stale_seconds.
            rej_ts = rejection.get("timestamp", "")
            if rej_ts:
                try:
                    rej_epoch = datetime.fromisoformat(
                        rej_ts.replace("Z", "+00:00")).timestamp()
                    rej_stale = int(time.time() - rej_epoch)
                    if not event or rej_stale < limits.stale_seconds:
                        limits.stale_seconds = rej_stale
                except Exception:
                    pass

    return limits


# ---- codex / opencode spend ------------------------------------------------

def _parse_codex() -> Optional[EngineSpend]:
    db = HOME / ".codex" / "state_5.sqlite"
    rows = _q(db, "SELECT SUM(tokens_used) FROM threads")
    if rows is None:
        return None
    total = (rows[0][0] or 0) if rows else 0
    if total == 0:
        return None
    return EngineSpend(tokens_combined=total)


def _parse_opencode() -> Optional[EngineSpend]:
    db = HOME / ".local" / "share" / "opencode" / "opencode.db"
    rows = _q(db, "SELECT SUM(tokens_input), SUM(tokens_output), SUM(cost) FROM session")
    if rows is None:
        return None
    ti, to, cost = rows[0] if rows else (0, 0, 0.0)
    ti, to, cost = ti or 0, to or 0, cost or 0.0
    if ti + to == 0:
        return None
    return EngineSpend(tokens_in=ti, tokens_out=to, cost=round(cost, 4))


# ---- public API ------------------------------------------------------------

def get_limits(cao_only: bool = True) -> LimitReport:
    """Collect limit/spend data from all engines. No API calls."""
    return LimitReport(
        claude=_parse_claude(cao_only),
        codex=_parse_codex(),
        opencode=_parse_opencode(),
        agy=None,
    )
```

- [ ] **Step 2: Quick sanity test**

Run: `cd run && python3 -c "from cao_limits import get_limits; r = get_limits(); print(r)"`
Expected: A `LimitReport` with real data from this machine.

- [ ] **Step 3: Commit**

```bash
git add run/cao_limits.py
git commit -m "feat: cao_limits core module — rate-limit parsing + spend aggregation"
```

---

### Task 3: Build the `cao-limits` CLI

**Files:**
- Create: `run/cao-limits`

**Interfaces:**
- Consumes: `cao_limits.get_limits() -> LimitReport`, `cao_lib.hn(n)`
- Produces: CLI output (human-readable table or `--json`)

- [ ] **Step 1: Create `run/cao-limits`**

```python
#!/usr/bin/env python3
"""cao-limits — engine quota status from on-disk data.

No API calls. Reads Claude rate-limit events from session logs and spend
totals for codex/opencode from their SQLite databases.

Usage:
  cao-limits              show quota status for all engines
  cao-limits --claude     Claude limits only (detailed)
  cao-limits --json       machine-readable JSON
  cao-limits --all-sessions  include non-CAO claude sessions (default: CAO-only)
  cao-limits -h | --help  show this help
"""
import json
import sys
import time
from datetime import datetime, timezone

from cao_lib import hn
from cao_limits import get_limits


# ---- visual bar ------------------------------------------------------------

BAR_CHARS = "░▓"  # empty, filled
BAR_WIDTH = 10


def bar(utilization):
    """Render a visual utilization bar like ░░░░░░░▓▓▓"""
    filled = max(0, min(BAR_WIDTH, int(utilization * BAR_WIDTH + 0.5)))
    return BAR_CHARS[1] * filled + BAR_CHARS[0] * (BAR_WIDTH - filled)


def status_label(status, blocked=False):
    if blocked:
        return "\033[1;31m✗ BLOCKED\033[0m"
    if status == "allowed_warning":
        return "\033[1;33m⚠ warning\033[0m"
    if status == "rejected":
        return "\033[1;31m✗ rejected\033[0m"
    return "allowed"


def fmt_resets(unix_ts):
    if not unix_ts:
        return ""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def fmt_stale(seconds):
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


# ---- views -----------------------------------------------------------------

def view_human(report):
    print()
    print("  cao-limits — engine quota status")
    print()

    # Claude
    cl = report.claude
    if cl is None:
        print("  CLAUDE")
        print("  └─ (no rate-limit data found in session logs)")
    else:
        stale = fmt_stale(cl.stale_seconds)
        print(f"  CLAUDE (data from {stale})")
        if cl.blocked:
            resets = fmt_resets(cl.blocked_resets_at)
            remaining = cl.blocked_resets_at - int(time.time())
            remaining_str = fmt_stale(-remaining).replace(" ago", "") if remaining > 0 else "now"
            print(f"  ├─ {status_label('', blocked=True)}  "
                  f"window: {cl.blocked_window}  "
                  f"resets: {resets} (in {remaining_str})")
        if cl.five_hour:
            w = cl.five_hour
            print(f"  ├─ 5-hour:  {bar(w.utilization)}  "
                  f"utilization {w.utilization:.0%}  "
                  f"{status_label(w.status)}  "
                  f"resets {fmt_resets(w.resets_at)}")
        if cl.seven_day:
            w = cl.seven_day
            connector = "└─" if not cl.five_hour else "└─"
            print(f"  {connector} 7-day:   {bar(w.utilization)}  "
                  f"utilization {w.utilization:.0%}  "
                  f"{status_label(w.status)}  "
                  f"resets {fmt_resets(w.resets_at)}")
        if not cl.five_hour and not cl.seven_day and not cl.blocked:
            print("  └─ (rate_limit_event found but no window data)")
    print()

    # Codex
    cx = report.codex
    print("  CODEX")
    if cx is None:
        print("  └─ (no usage data)")
    else:
        print(f"  └─ spend: {hn(cx.tokens_combined)} tokens (no local ceiling data)")
    print()

    # Opencode
    oc = report.opencode
    print("  OPENCODE")
    if oc is None:
        print("  └─ (no usage data)")
    else:
        total = oc.tokens_in + oc.tokens_out
        cost_str = f"  ${oc.cost:.2f}" if oc.cost else ""
        print(f"  └─ spend: {hn(total)} tokens (in {hn(oc.tokens_in)} / "
              f"out {hn(oc.tokens_out)}){cost_str} (no local ceiling data)")
    print()

    # Agy
    print("  AGY / GEMINI")
    print("  └─ (no local usage log — quota is server-side)")
    print()


def view_json(report):
    out = {}

    if report.claude:
        cl = report.claude
        out["claude"] = {
            "stale_seconds": cl.stale_seconds,
            "blocked": cl.blocked,
        }
        if cl.blocked:
            out["claude"]["blocked_window"] = cl.blocked_window
            out["claude"]["blocked_resets_at"] = cl.blocked_resets_at
        if cl.five_hour:
            out["claude"]["five_hour"] = {
                "utilization": cl.five_hour.utilization,
                "status": cl.five_hour.status,
                "resets_at": cl.five_hour.resets_at,
            }
        if cl.seven_day:
            out["claude"]["seven_day"] = {
                "utilization": cl.seven_day.utilization,
                "status": cl.seven_day.status,
                "resets_at": cl.seven_day.resets_at,
            }
    else:
        out["claude"] = None

    if report.codex:
        out["codex"] = {"tokens_used": report.codex.tokens_combined}
    else:
        out["codex"] = None

    if report.opencode:
        out["opencode"] = {
            "tokens_in": report.opencode.tokens_in,
            "tokens_out": report.opencode.tokens_out,
            "cost": report.opencode.cost,
        }
    else:
        out["opencode"] = None

    out["agy"] = None
    print(json.dumps(out, indent=2))


# ---- main ------------------------------------------------------------------

KNOWN_FLAGS = {"--json", "--claude", "--all-sessions", "-h", "--help"}


def main():
    args = sys.argv[1:]

    if "-h" in args or "--help" in args:
        print(__doc__.rstrip())
        return

    for a in args:
        if a.startswith("-") and a not in KNOWN_FLAGS:
            sys.exit(f"unknown flag '{a}'. Run: cao-limits --help")

    as_json = "--json" in args
    cao_only = "--all-sessions" not in args

    report = get_limits(cao_only=cao_only)

    if as_json:
        view_json(report)
    else:
        view_human(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x run/cao-limits
```

- [ ] **Step 3: Test CLI output**

Run: `python3 run/cao-limits`
Expected: Human-readable output showing Claude quota status and engine spend.

Run: `python3 run/cao-limits --json`
Expected: JSON output with claude/codex/opencode/agy keys.

- [ ] **Step 4: Commit**

```bash
git add run/cao-limits
git commit -m "feat: cao-limits CLI — engine quota status from on-disk data"
```

---

### Task 4: Wire into bootstrap (symlink + doctor stale check)

**Files:**
- Modify: `1_install/bootstrap.sh` (add `cao-limits` symlink)
- Modify: `run/cao-doctor` (add `cao-limits` to the stale-tools list)

**Interfaces:**
- Consumes: `run/cao-limits` exists as a file
- Produces: `~/.local/bin/cao-limits` symlink; `cao-doctor` checks it for staleness

- [ ] **Step 1: Add `cao-limits` to bootstrap symlink list**

In `1_install/bootstrap.sh`, find where `cao-tokens` / `cao-plugins` are symlinked and add `cao-limits` to the same loop/list.

- [ ] **Step 2: Add `cao-limits` to cao-doctor stale check**

In `run/cao-doctor` line 48, the tool list is:
```bash
for tool in cao-run cao-doctor cao-stop cao-tokens cao-plugins; do
```
Add `cao-limits`:
```bash
for tool in cao-run cao-doctor cao-stop cao-tokens cao-plugins cao-limits; do
```

- [ ] **Step 3: Create the symlink now (without re-running bootstrap)**

```bash
ln -sf "$(pwd)/run/cao-limits" ~/.local/bin/cao-limits
```

- [ ] **Step 4: Verify**

Run: `cao-limits`
Expected: Same output as `python3 run/cao-limits`.

Run: `cao-doctor`
Expected: `cao-limits` shows up in D1 as a fresh tool (not stale).

- [ ] **Step 5: Commit**

```bash
git add 1_install/bootstrap.sh run/cao-doctor
git commit -m "feat: wire cao-limits into bootstrap symlinks + doctor stale check"
```

---

### Task 5: End-to-end verification

**Files:** None (read-only verification)

- [ ] **Step 1: Verify `cao-tokens` unchanged**

Run: `cao-tokens --since 7d`
Expected: Same output as before the refactor.

- [ ] **Step 2: Verify `cao-limits` with real data**

Run: `cao-limits`
Expected: Shows Claude rate-limit status from the real session data discovered earlier (the five_hour + seven_day window data).

Run: `cao-limits --json`
Expected: Machine-readable JSON matching the spec.

- [ ] **Step 3: Verify Python API**

Run: `python3 -c "from cao_limits import get_limits; r = get_limits(); print(f'claude blocked: {r.claude.is_blocked() if r.claude else None}'); print(f'claude near limit: {r.claude.is_near_limit() if r.claude else None}')"`
Expected: Prints `blocked: False/True` and `near_limit: True/False` based on actual data.

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A
git status  # verify nothing unexpected
git commit -m "feat(v2): cao-limits — engine quota status tool (v2 step 1)"
git push
```
