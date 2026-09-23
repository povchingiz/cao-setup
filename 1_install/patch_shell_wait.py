#!/usr/bin/env python3
"""Idempotently patch CAO's ``wait_for_shell`` so shell readiness is read from
the live tmux pane when the FIFO pipeline has not delivered anything yet.

Symptom without this patch (reproduced locally, ~50% of launches):

    Error: Failed to connect to cao-server: HTTPConnectionPool(... port=9889):
           Read timed out. (read timeout=30)
    server.log: Failed to create terminal: Shell initialization timed out after 60s

Mechanism: ``terminal_service.create_terminal`` attaches ``tmux pipe-pane`` to a
FIFO, and ``wait_for_shell`` waits for the StatusMonitor buffer — which is fed
only by that FIFO — to become non-empty and stable. The FIFO reader thread does
read the shell's prompt bytes (the watchdog observes ``ever_delivered=True``
~2s in, and LogWriter's ``logs/terminal/<id>.log`` ends up with the full 1031
bytes), but it does not publish them to the event bus until teardown ~60s
later, so the StatusMonitor buffer stays empty and the wait times out. The
pane itself has the prompt the whole time.

The patch keeps the existing buffer as the primary source and falls back to
``backend.get_history()`` (the same call the pipe-liveness watchdog already
makes) whenever the buffer is still blank. Readiness then no longer depends on
the FIFO delivering its first chunk.

Safe to run repeatedly. Re-run after every `cao update` / reinstall.
"""
import sys
from pathlib import Path

CANDIDATES = [
    Path.home() / ".local/share/uv/tools/cli-agent-orchestrator/lib",
    Path.home() / ".local/share/uv/tools/cli-agent-orchestrator",
]

MARKER = "# wcao: pane fallback for an undelivered FIFO first chunk"

OLD = """    else:

        def read_buffer() -> str:
            return status_monitor.get_buffer(terminal_id)
"""

NEW = """    else:
        # wcao: pane fallback for an undelivered FIFO first chunk
        pipe_window = _resolve_window(terminal_id)

        def read_buffer() -> str:
            buf = status_monitor.get_buffer(terminal_id)
            if buf.strip() or pipe_window is None:
                return buf
            # The FIFO has not published its first chunk yet. tmux's own pane
            # content is authoritative for "is the shell up", so use it rather
            # than waiting out the full init timeout on an empty buffer.
            try:
                return backend.get_history(pipe_window[0], pipe_window[1], strip_escapes=True)
            except Exception as e:
                logger.debug(f"wait_for_shell [{terminal_id}]: pane fallback read failed: {e}")
                return ""
"""


def find_terminal_utils() -> Path | None:
    for base in CANDIDATES:
        if not base.exists():
            continue
        for p in base.rglob("cli_agent_orchestrator/utils/terminal.py"):
            return p
    return None


def main() -> int:
    target = find_terminal_utils()
    if target is None:
        print("ERROR: cli_agent_orchestrator/utils/terminal.py not found under the CAO venv.", file=sys.stderr)
        print("Is cli-agent-orchestrator installed via uv tool?", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"OK  already patched: {target}")
        return 0
    if OLD not in text:
        # Neither our marker nor the original body: CAO changed upstream, or a
        # previous patch was partially undone. Either way the fallback is NOT
        # in place, so report failure - exiting 0 here would let cao-run's
        # self-repair silently no-op and launches would time out again.
        print(f"WARN wait_for_shell body not found (CAO changed?): {target}", file=sys.stderr)
        print("     Inspect manually; shell-readiness may already read the pane.", file=sys.stderr)
        return 2

    target.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"OK  patched: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
