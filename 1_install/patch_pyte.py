#!/usr/bin/env python3
"""Idempotently patch pyte's Screen.select_graphic_rendition to accept the
non-standard ``private`` kwarg that the Antigravity CLI emits (CSI ? ... m).

Without this, pyte 0.8.x raises:
    TypeError: Screen.select_graphic_rendition() got an unexpected keyword
    argument 'private'
which kills CAO's StatusMonitor thread whenever an Antigravity worker renders.

Finds pyte inside the CAO uv-tool venv and rewrites the method signature in
place. Safe to run repeatedly. Re-run after every `cao update` / reinstall.
"""
import re
import sys
from pathlib import Path

CANDIDATES = [
    Path.home() / ".local/share/uv/tools/cli-agent-orchestrator/lib",
    Path.home() / ".local/share/uv/tools/cli-agent-orchestrator",
]

OLD = "def select_graphic_rendition(self, *attrs: int) -> None:"
NEW = "def select_graphic_rendition(self, *attrs: int, private: bool = False) -> None:"


def find_pyte_screens() -> Path | None:
    for base in CANDIDATES:
        if not base.exists():
            continue
        for p in base.rglob("pyte/screens.py"):
            return p
    return None


def main() -> int:
    screens = find_pyte_screens()
    if screens is None:
        print("ERROR: pyte/screens.py not found under the CAO venv.", file=sys.stderr)
        print("Is cli-agent-orchestrator installed via uv tool?", file=sys.stderr)
        return 1

    text = screens.read_text(encoding="utf-8")
    if NEW in text:
        print(f"OK  already patched: {screens}")
        return 0
    if OLD not in text:
        print(f"WARN signature not found (pyte changed?): {screens}", file=sys.stderr)
        print("     Inspect manually; the private-kwarg fix may be unnecessary.", file=sys.stderr)
        return 0

    screens.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"OK  patched: {screens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
