"""cao_limits — engine quota status: "how much is left?"

cao-tokens answers "how much did I spend?". This module answers the other
half — how close each engine is to its ceiling.

Only Claude publishes a real ceiling on disk. It does so in two places, both
of which we read (see `_scan_claude`):

  A. `rate_limit_event`  — proactive warning, carries per-window utilization.
  B. `quotaLimits`       — the 429 rejection, binary but authoritative.

Codex and opencode expose spend only (no local ceiling data); agy/gemini keeps
its quota server-side and writes nothing locally, so it is always None.

No probing, no API calls — everything here reads files already on disk.
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from glob import glob
from typing import Optional

try:
    from cao_lib import HOME, _file_is_cao, _iter_claude_files, _q
except ImportError:
    from run.cao_lib import HOME, _file_is_cao, _iter_claude_files, _q

# Windows Claude reports in `unifiedWindows`, in the order we display them.
WINDOWS = ("five_hour", "seven_day")

# Statuses that mean the request was refused outright, not merely warned about.
BLOCKED_STATUSES = ("rejected",)

# Utilization above this counts as "near limit" even with a plain `allowed`.
NEAR_LIMIT_UTILIZATION = 0.8

CODEX_DB = HOME / ".codex" / "state_5.sqlite"
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"


# --------------------------------------------------------------------------
# dataclasses
# --------------------------------------------------------------------------

@dataclass
class WindowInfo:
    """One rate-limit window (five_hour or seven_day) as Claude reported it."""

    utilization: float = 0.0
    resets_at: int = 0          # Unix timestamp (seconds) — NOT ISO
    status: str = "unknown"

    @property
    def resets_at_iso(self) -> Optional[str]:
        """`resets_at` rendered as a UTC ISO-8601 string, or None if unset."""
        if not self.resets_at:
            return None
        dt = datetime.fromtimestamp(self.resets_at, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def resets_in_seconds(self) -> int:
        """Seconds until this window resets; 0 once the reset time has passed."""
        if not self.resets_at:
            return 0
        return max(0, int(self.resets_at - time.time()))


@dataclass
class ClaudeLimits:
    """Claude's limit state, merged from both on-disk sources."""

    five_hour: Optional[WindowInfo] = None
    seven_day: Optional[WindowInfo] = None
    blocked: bool = False
    blocked_window: str = ""     # rateLimitType of the 429, e.g. "five_hour"
    blocked_resets_at: int = 0   # Unix timestamp the block lifts
    stale_seconds: int = 0       # age of the newest data point we found
    source_file: str = ""

    def is_near_limit(self) -> bool:
        """True if any window is over threshold, warning, or already blocked."""
        if self.blocked:
            return True
        for win in (self.five_hour, self.seven_day):
            if win is None:
                continue
            if win.utilization > NEAR_LIMIT_UTILIZATION:
                return True
            if win.status == "allowed_warning":
                return True
        return False

    def is_blocked(self) -> bool:
        """True if Claude refused a request and the reset time hasn't passed."""
        if not self.blocked:
            return False
        # A rejection is only current until its window resets; past that it is
        # history, not state.
        if self.blocked_resets_at and self.blocked_resets_at <= time.time():
            return False
        return True

    @property
    def blocked_resets_at_iso(self) -> Optional[str]:
        if not self.blocked_resets_at:
            return None
        dt = datetime.fromtimestamp(self.blocked_resets_at, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class EngineSpend:
    """Spend totals for an engine that publishes no ceiling locally."""

    tokens_in: int = 0
    tokens_out: int = 0
    tokens_combined: int = 0   # codex reports one number, not a split
    cost: float = 0.0          # opencode only; others have no local $ data


@dataclass
class LimitReport:
    """Everything `get_limits()` could determine, per engine."""

    claude: Optional[ClaudeLimits] = None
    codex: Optional[EngineSpend] = None
    opencode: Optional[EngineSpend] = None
    agy: None = None           # quota is server-side; nothing is ever on disk
    timestamp: float = field(default_factory=time.time)


# --------------------------------------------------------------------------
# claude parsing
# --------------------------------------------------------------------------

def _parse_rate_limit_event(line):
    """Pull `rate_limit_info` out of one `rate_limit_event` line.

    Returns the info dict, or None if the line isn't one of ours. The .txt
    files these live in are captured stream-json output and carry plain-text
    header lines too, so a failed json parse is normal, not an error.
    """
    if '"rate_limit_event"' not in line:
        return None
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or obj.get("type") != "rate_limit_event":
        return None
    info = obj.get("rate_limit_info")
    return info if isinstance(info, dict) else None


def _parse_quota_limits(line):
    """Pull `quotaLimits` out of one 429 rejection line in a session jsonl."""
    if '"quotaLimits"' not in line:
        return None
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    quota = obj.get("quotaLimits")
    if not isinstance(quota, dict):
        return None
    # Only the rate-limit rejections interest us; other quotaLimits rows are
    # informational and carry no ceiling signal.
    if obj.get("error") != "rate_limit":
        return None
    return quota


def _windows_from_info(info):
    """Build WindowInfo objects from a `rate_limit_info` dict.

    `unifiedWindows` is the rich source (utilization per window). When it is
    absent we fall back to the flat `rateLimitType` + `utilization` pair, which
    only describes the single window that tripped.
    """
    status = info.get("status", "unknown")
    out = {w: None for w in WINDOWS}

    unified = info.get("unifiedWindows")
    if isinstance(unified, dict):
        for name in WINDOWS:
            win = unified.get(name)
            if not isinstance(win, dict):
                continue
            out[name] = WindowInfo(
                utilization=float(win.get("utilization") or 0.0),
                resets_at=int(win.get("resetsAt") or 0),
                status=status,
            )

    # Flat fallback: fills in a window unifiedWindows didn't describe.
    kind = info.get("rateLimitType")
    if kind in WINDOWS and out[kind] is None:
        out[kind] = WindowInfo(
            utilization=float(info.get("utilization") or 0.0),
            resets_at=int(info.get("resetsAt") or 0),
            status=status,
        )
    return out


def _iter_tool_result_files(cutoff):
    """Yield `tool-results/*.txt` paths under Claude session dirs.

    Mirrors `_iter_claude_files`' mtime prefilter — these files can be large
    and most will predate the cutoff.
    """
    root = HOME / ".claude" / "projects"
    if not root.exists():
        return
    pattern = str(root / "**" / "tool-results" / "*.txt")
    for f in glob(pattern, recursive=True):
        try:
            if cutoff and os.path.getmtime(f) < cutoff:
                continue
        except OSError:
            continue
        yield f


def _session_jsonl_for(tool_result_path):
    """Map `<project>/<session_id>/tool-results/x.txt` to `<session_id>.jsonl`.

    The CAO filter works on session jsonl files, but rate_limit_events live in
    a sibling directory. This resolves one to the other so the same
    `_file_is_cao` check applies to both sources.
    """
    session_dir = os.path.dirname(os.path.dirname(tool_result_path))
    return session_dir + ".jsonl"


def _scan_claude(cao_only=True, cutoff=0.0):
    """Scan both Claude sources and merge the newest signal from each.

    Returns a ClaudeLimits, or None when no rate-limit data exists anywhere
    (a fresh install, or an account that has simply never been warned).
    """
    newest_event = None      # (mtime, info dict, path)
    newest_rejection = None  # (mtime, quota dict, path)

    # Source A — proactive warnings with per-window utilization.
    for path in _iter_tool_result_files(cutoff):
        if cao_only and not _file_is_cao(_session_jsonl_for(path)):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if newest_event and mtime <= newest_event[0]:
            # An older file cannot beat what we already have; skip the read.
            continue
        latest = None
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    info = _parse_rate_limit_event(line)
                    if info:
                        latest = info  # last one in the file wins
        except OSError:
            continue
        if latest is not None:
            newest_event = (mtime, latest, path)

    # Source B — hard 429 rejections in the main session logs.
    for path in _iter_claude_files(cutoff):
        if cao_only and not _file_is_cao(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if newest_rejection and mtime <= newest_rejection[0]:
            continue
        latest = None
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    quota = _parse_quota_limits(line)
                    if quota:
                        latest = quota
        except OSError:
            continue
        if latest is not None:
            newest_rejection = (mtime, latest, path)

    if not newest_event and not newest_rejection:
        return None

    limits = ClaudeLimits()

    if newest_event:
        mtime, info, path = newest_event
        windows = _windows_from_info(info)
        limits.five_hour = windows["five_hour"]
        limits.seven_day = windows["seven_day"]
        limits.source_file = path

    if newest_rejection:
        mtime, quota, path = newest_rejection
        if quota.get("status") in BLOCKED_STATUSES:
            limits.blocked = True
            limits.blocked_window = quota.get("rateLimitType") or ""
            limits.blocked_resets_at = int(quota.get("resetsAt") or 0)
            # A rejection outranks a warning: if it is the newer of the two,
            # it names the source file, and it stamps the window it hit.
            if not newest_event or mtime >= newest_event[0]:
                limits.source_file = path
            win = getattr(limits, limits.blocked_window, None) \
                if limits.blocked_window in WINDOWS else None
            if win is not None:
                win.status = quota["status"]
            elif limits.blocked_window in WINDOWS:
                # No utilization data for that window, but we know it tripped.
                setattr(limits, limits.blocked_window, WindowInfo(
                    utilization=1.0,
                    resets_at=limits.blocked_resets_at,
                    status=quota["status"],
                ))

    newest_mtime = max(
        m for m in (
            newest_event[0] if newest_event else None,
            newest_rejection[0] if newest_rejection else None,
        ) if m is not None
    )
    limits.stale_seconds = max(0, int(time.time() - newest_mtime))
    return limits


# --------------------------------------------------------------------------
# other engines — spend only, no ceiling exists locally
# --------------------------------------------------------------------------

def _scan_codex():
    rows = _q(str(CODEX_DB), "SELECT SUM(tokens_used) FROM threads")
    if not rows or rows[0][0] is None:
        return None
    total = int(rows[0][0])
    return EngineSpend(tokens_combined=total)


def _scan_opencode():
    rows = _q(
        str(OPENCODE_DB),
        "SELECT SUM(tokens_input), SUM(tokens_output), SUM(cost) FROM session",
    )
    if not rows or rows[0][0] is None:
        return None
    tin, tout, cost = rows[0]
    return EngineSpend(
        tokens_in=int(tin or 0),
        tokens_out=int(tout or 0),
        tokens_combined=int(tin or 0) + int(tout or 0),
        cost=float(cost or 0.0),
    )


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def get_limits(cao_only: bool = True) -> LimitReport:
    """Read limits from all engines. Never raises; missing engines report None."""
    return LimitReport(
        claude=_scan_claude(cao_only=cao_only),
        codex=_scan_codex(),
        opencode=_scan_opencode(),
    )


def get_claude_limits(cao_only: bool = True) -> Optional[ClaudeLimits]:
    """Public helper returning current ClaudeLimits or None."""
    return _scan_claude(cao_only=cao_only)
