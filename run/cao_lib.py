"""cao_lib — shared helpers for cao-tokens, cao-limits, and future tools.
Extracted from cao-tokens to avoid duplication."""
import json
import os
import sqlite3
import sys
import time
from glob import glob
from pathlib import Path

HOME = Path.home()

CAO_MARKERS = ("cao-mcp-server", "cao_", '"assign"')


def cutoff_ts(since):
    if not since:
        return 0.0
    n, unit = float(since[:-1]), since[-1]
    mult = {"h": 3600, "d": 86400, "w": 604800}.get(unit)
    if not mult:
        sys.exit(f"bad --since '{since}': use e.g. 24h, 7d, 2w")
    return time.time() - n * mult


def _iter_claude_files(cutoff):
    root = HOME / ".claude" / "projects"
    if not root.exists():
        return
    for f in glob(str(root / "**" / "*.jsonl"), recursive=True):
        if cutoff and os.path.getmtime(f) < cutoff:
            continue
        yield f


def _file_is_cao(path):
    """True if this session loaded cao's MCP server / used its assign tool."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if any(m in line for m in CAO_MARKERS):
                    return True
    except OSError:
        return False
    return False


def _q(db, sql):
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
