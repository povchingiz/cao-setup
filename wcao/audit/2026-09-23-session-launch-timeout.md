# Incident report — supervisor launch fails with a 30s client timeout

*Investigated 2026-09-23. Environment: Linux 7.0.0-30-generic, tmux 3.6, `cli-agent-orchestrator` 2.5.0 on Python 3.14 (uv tool), `claude` 2.1.280.*

## 1. Reported symptom

`cao-run` passed every `cao-doctor` gate (15 passed / 1 warning / 0 failed), started the daemon, then:

```
Error: Failed to connect to cao-server: HTTPConnectionPool(host='127.0.0.1', port=9889):
       Read timed out. (read timeout=30)
⚠ Supervisor launch on 'claude_code' failed — likely Claude quota/login.
  Auto-retrying on fallback engine 'antigravity_cli'...
Error: Failed to connect to cao-server: 400 Client Error: Bad Request for url:
       http://127.0.0.1:9889/sessions?...&session_name=supervisor-wprojects&...
```

Both messages are misleading. Neither the port, nor Claude's quota, nor the fallback engine was at fault.

## 2. What the messages actually meant

**The port was reachable the whole time.** `ss -ltnp` showed `cao-server` listening on `127.0.0.1:9889`, and `GET /health` returned `200` during the failure window. The "failed to connect" wording comes from the CLI's generic request wrapper; the real event was a **read** timeout at 30 s on `POST /sessions`, which is the server taking longer than the client will wait.

**The server-side error was:**

```
cli_agent_orchestrator.utils.terminal   - WARNING - Timeout waiting for shell to be ready for <tid>
cli_agent_orchestrator.services.terminal_service - ERROR - Failed to create terminal:
                                          Shell initialization timed out after 60s
```

**The 400 was a cascade, not a second defect.** The timed-out `claude_code` attempt kept running server-side and had already registered the tmux session `cao-supervisor-wprojects`. The fallback retry reused the same `--session-name`, so it hit `Session 'cao-supervisor-wprojects' already exists` → `400`. Confirmed by replaying the request against a live session name.

## 3. Root cause

`terminal_service.create_terminal` sets up output streaming as:

```
tmux pipe-pane  →  FIFO  →  FifoManager reader thread  →  event bus  →  StatusMonitor buffer
```

`utils/terminal.py::wait_for_shell` then polls `status_monitor.get_buffer(terminal_id)` and returns ready once that buffer is non-empty and unchanged for 2 s. For tmux (a pipe-pane backend) that buffer is the **only** source it consults.

**The FIFO reader pulls the shell's prompt bytes but does not publish them to the event bus for ~60 s.** Measured on an instrumented build:

| Observation | Healthy launch | Failing launch |
|---|---|---|
| `os.read` off the FIFO | `n=456` @ +0.00s, `n=575` @ +0.004s | `n=456` @ +0.00s, `n=472` @ +0.002s |
| reader flush → `bus.publish` | +0.051s (one `_COALESCE_WINDOW`) | **never, until teardown at +62s** |
| watchdog `ever_delivered` | `True` @ +2s | `True` @ +2s |
| `logs/terminal/<tid>.log` (LogWriter) | 1031 bytes | 1031 bytes (arrives at teardown) |
| `StatusMonitor recv` | +0.052s | **+62s** |
| tmux pane content (`get_history`) | 378 chars @ +2s | 378 chars @ +2s |

So: tmux forwards correctly, `pipe-pane` is attached (`pane_pipe=1`), `cat` holds the FIFO write end, the reader thread reads the bytes — and then stalls with them in `pending` until `stop_reader` runs the `finally` flush. `wait_for_shell` sees an empty buffer for the full 60 s and raises.

**Reproduction rate: 6/6 failures** on back-to-back `POST /sessions` calls; roughly 50 % when launches are spaced out. Provider-independent (reproduced on `claude_code`; `antigravity_cli` shares the same pre-provider code path).

### Why the built-in self-healing does not catch it

`FifoManager` has a cold-start rescue for exactly this class of bug (`harness-control#93`): if the FIFO has delivered nothing within `PIPE_LIVENESS_COLD_START_GRACE_S` while the pane has content, it re-arms `pipe-pane` and replays the pane snapshot straight to the event bus. It never fires here, because its guard is `not ever_delivered` — and the FIFO *did* deliver bytes to the reader thread. The divergence check cannot fire either: it needs the pane to change, and a shell sitting on a static prompt never does. The terminal falls between both detectors.

### Not root-caused

The reason the reader thread stalls is still open. A `faulthandler` dump taken during a stall put the thread at `fifo_reader.py:325` (`os.read(read_fd, CHUNK_SIZE)`), but `/proc/<pid>/fdinfo/<fd>` reported `flags: 02104000` — `O_NONBLOCK` set — on that same FIFO at that same moment, and a non-blocking read cannot block. The select timeout in that loop is `_COALESCE_WINDOW` (0.05 s), so neither call should park for 62 s. `py-spy` could not attach (`ptrace_scope` restricted), so the contradiction was not resolved. The loop is not spinning: the process sat at ~1 % CPU throughout.

Suspected but unproven: contention on `FifoManager._lock`, which the reader takes on every chunk and the liveness watchdog takes on every check.

## 4. Fixes applied

### 4.1 `1_install/patch_shell_wait.py` (new)

Idempotent patch of the installed `cli_agent_orchestrator/utils/terminal.py`, in the same style as the existing `patch_pyte.py`. `wait_for_shell` keeps the StatusMonitor buffer as its primary source and falls back to `backend.get_history()` — the live tmux pane, the same call the pipe-liveness watchdog already makes — whenever that buffer is still blank:

```python
def read_buffer() -> str:
    buf = status_monitor.get_buffer(terminal_id)
    if buf.strip() or pipe_window is None:
        return buf
    try:
        return backend.get_history(pipe_window[0], pipe_window[1], strip_escapes=True)
    except Exception as e:
        logger.debug(f"wait_for_shell [{terminal_id}]: pane fallback read failed: {e}")
        return ""
```

Shell readiness no longer depends on the FIFO delivering its first chunk. Wired into `1_install/bootstrap.sh` next to the pyte patch.

### 4.2 `run/cao-run` — reap before fallback

The existing `is_session_busy` guard only matches the string `already exists`, which a *client-side* read timeout never produces. The fallback therefore retried into a name the dead primary had already claimed. `cao-run` now deletes the half-created session (`DELETE /sessions/<name>`, `tmux kill-session`) and waits for the name to free up before the retry.

## 5. Verification

| Check | Before | After |
|---|---|---|
| 6 back-to-back `POST /sessions` (`claude_code`) | 0/6 | **6/6**, all reached `idle` |
| `cao-run --project vtest` end-to-end | 30 s timeout → 400 cascade | supervisor live in tmux, Claude Code attached |
| `uv run --with pytest pytest tests/` | 56 passed | **56 passed** |

Both fallback paths were exercised after the fix: launches whose FIFO delivered normally report `Shell ready (buffer stable, 1031 bytes)`; launches that stalled report `326 bytes` (the pane snapshot) and proceed to `idle` identically.

## 6. Open items

| # | Item | Severity | Owner |
|---|---|---|---|
| 1 | FIFO reader stall not root-caused — the patch bypasses the shell-readiness gate only. Downstream status detection still rides the same pipeline; it has not been seen to stall once the agent is producing output, but the failure mode is not eliminated. | High | upstream CAO |
| 2 | `1_install/patch_shell_wait.py` edits `site-packages` and is erased by `cao update` / reinstall. Re-run it (or `bootstrap.sh`) after every upgrade. Same constraint as `patch_pyte.py`. | Medium | wcao |
| 3 | `~/.aws/opencode/opencode.json` resolves `apiKey: "{env:LOCAL_API_KEY}"`, and the key is **not** in the shell environment — it lives in `~/.config/cao/cao.env` and `wcao/.env`, which `cao-run` and `cao-doctor` source at startup and pass to the daemon. So the supported entry point is fine. A daemon started by hand (`cao-server` directly, as this investigation did) inherits no key, and every `opencode_cli` worker it spawns fails authentication with no obvious cause. Worth a doctor check or a startup warning. | Medium | wcao |
| 4 | A failed terminal leaks its FIFO reader thread (`FIFO reader thread for terminal <tid> did not exit within 2s; leaking a daemon thread`) and leaves a `*.fifo` file behind. Accumulates across retries. | Low | upstream CAO |
| 5 | Every pane prints `-bash: /home/chingiz/snap/code/241/.local/share/../bin/env: No such file or directory` twice at startup — stale VSCode-snap shell integration in `~/.bashrc`. Cosmetic; it pollutes the first captured frame. | Low | operator |
| 6 | Cold-start rescue in `FifoManager` is unreachable for this failure shape (`ever_delivered` is `True`). Worth reporting upstream: the guard should key off "nothing *published*" rather than "nothing read". | Medium | upstream CAO |
| 7 | Worker lifecycle (`assign` / handoff) was not exercised — only supervisor launch. | Medium | wcao |

## 7. How to reproduce the original failure

```bash
# with the patch reverted
tmux kill-server
for i in 1 2 3; do
  curl -s -m 70 -X POST "http://127.0.0.1:9889/sessions\
?agent_profile=code_supervisor&working_directory=$PWD\
&provider=claude_code&session_name=repro$i&allowed_tools=%2A"
done
# → {"detail":"Failed to create session: Shell initialization timed out after 60s"}
```

Useful evidence trail: `~/.cao/logs/server.log` (summary), `~/.aws/cli-agent-orchestrator/logs/cao_<ts>.log` (detail; `CAO_LOG_LEVEL=DEBUG cao-server` for more), `~/.aws/cli-agent-orchestrator/logs/terminal/<tid>.log` (what the FIFO actually carried).

---

## 8. Resolution as landed on master (2026-09-23)

The fixes in §4 landed with changes; open items #2, #3 and #6 are addressed.

| Commit | What |
|---|---|
| `7efc80b` | `patch_shell_wait.py` + bootstrap wiring + the `cao-run` reap (§4.1, §4.2). The reap uses the unprefixed session name for the API and the `cao-` prefixed one for tmux - the branch used the tmux name for both. |
| `a8bd195` | `run/_cao_common.sh`: `.env` and port resolution no longer depend on the repo's location (open item #3). Search order is `$CAO_ENV_FILE`, `<repo>/.env`, `$PWD/.env`, `~/.config/cao/cao.env`, and it keeps looking until `LOCAL_API_KEY` is actually set. `cao-doctor` reports which file supplied it. |
| `61cb415` | Worker aliases kept distinct, enforced in `render_config.validate()`. |
| `33352c4` | `cao-doctor` D5-D8: launch smoke test (`--deep`), config/runtime drift, daemon env, patch integrity. D5 is the check that would have caught this incident - the original run reported 15 passed / 1 warning / 0 failed. |
| `93eb8d2` | `run/cao-patch` reapplies site-packages patches; `cao-run` self-repairs at startup (open item #2). |

Two things found while implementing:

1. **`patch_shell_wait.py` exited 0 when it could not apply.** With neither its
   marker nor the original body present it warned and returned success, so the
   self-repair in `cao-run` would no-op while reporting that patches were
   applied - the same silent failure this incident was about. It now exits 2.
2. **`2_configure/cao.config.local.toml` overrides the tracked config and is
   gitignored.** Edits to `cao.config.toml` alone do not affect the running
   system. This is what let the live supervisor table drift to 4 workers,
   naming an `opencode_worker` that no longer exists; `cao-doctor` D6 now
   detects that class of drift.

Still open: **#1** (the FIFO reader stall itself is not root-caused - the patch
bypasses the shell-readiness gate, it does not fix the pipeline), **#4** (leaked
FIFO reader threads), **#5** (cosmetic stale VSCode shell integration), and
**#7** (worker lifecycle never exercised). #1 and #6 belong upstream.
