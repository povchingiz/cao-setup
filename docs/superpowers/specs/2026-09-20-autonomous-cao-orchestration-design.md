# Autonomous CAO Orchestration & Self-Healing Execution Design

## Executive Summary
This design specifies the end-to-end autonomous execution architecture for `cao-setup`. It introduces a **Hybrid Model**: interactive planning between the developer and a CAO supervisor up front, transitioning seamlessly into an autonomous execution loop (`cao-auto`) that dispatches worker agents in parallel, auto-routes around quota/429 limits using a universal OpenCode fallback ladder, self-heals blocker findings via an automated Audit Gate, and emits real-time telemetry to `cao-monitor` and Telegram.

---

## 1. System Architecture & Lifecycle

```
[Phase 1: Interactive Planning] (Supervisor in tmux)
  │  • Requirements & design alignment (produces cao_session/design/<name>.mmd)
  │  • Compiles tasks into cao_session/session_NNN/tasks.json with Tiered Models
  │  • Human approves: "proceed"
  ▼
[Supervisor kicks off autonomous routine]
  │  • Prints: "Starting autonomous execution. You can now detach (Ctrl-b d)."
  │  • Launches background execution engine (run/cao-auto)
  ▼ (Human detaches / walks away)
[Phase 2: Autonomous Execution] (Headless Engine)
  │  • Evaluates DAG (depends_on) & file disjointness
  │  • Dispatches ready tasks to CAO workers (max_concurrent_workers cap)
  │  • Monitors terminal states via CAO Server REST API (port 9889)
  │  • Catches 429/quota limits -> auto-swaps to coder_worker (DeepSeek-V4-Pro)
  │  • Updates tasks.json live (tracked by cao-monitor --watch)
  │  • Emits key events to Telegram (bot token / chat ID in cao.env)
  ▼
[Phase 3: Autonomous Audit Gate & Test Suite]
  │  • Dispatches antigravity_worker to audit diff (reports/audit.md)
  │  • Executes project test suite (pytest, npm test, cao-aggressive)
  │  • If BLOCKER found: auto-generates fix-task -> assigns to owning worker -> re-audits
  ▼ (0 Blockers)
[Session Complete & Final Telegram Alert]
```

---

## 2. Model Quota Tiering & Universal Fallback

To maximize value from cloud subscriptions while maintaining 100% uptime:

### Tier 1 (Priority Cloud Subscriptions — Exhaust First):
* **Architecture, Contracts, Core Reasoning:** `claude_worker` (`claude_code` / Opus 4.8 / Sonnet)
* **Frontend, UI Components:** `codex_worker` (`codex` / GPT)
* **Structured Audits, QA, Large-Context Maps:** `antigravity_worker` / `analyst_worker` (`antigravity_cli` / Gemini 3.1 Pro / Claude)

### Tier 2 (Universal Catch-All Fallback — Everywhere):
* **High-Throughput Bulk Coding:** `coder_worker` (`opencode_cli` with `deepseek-ai/DeepSeek-V4-Pro` / Kimi-K3 / GLM on Nitec endpoint).
* Metered, vast token capacity, completely unconstrained by cloud subscription rate-limit windows.

### Autonomous Fallback Trigger:
If any Tier 1 worker returns `429`, `rate limit`, `quota exceeded`, `usage limit`, or fails to spawn:
1. The execution engine immediately captures the failure and terminates the failed worker pane.
2. The task in `tasks.json` is updated:
   * `engine` -> `fallback_engine` (`coder_worker`)
   * `model` -> `fallback_model` (`deepseek-ai/DeepSeek-V4-Pro`)
   * Appends to `comments`:
     `{"by": "orchestrator", "at": "<iso_timestamp>", "text": "Tier 1 quota exceeded on <worker> -> auto-swapped to coder_worker (DeepSeek-V4-Pro)"}`
3. Immediately dispatches `coder_worker` via CAO API.
4. Emits a Telegram notification:
   `"⚠️ Task <id> (<title>): <worker> hit quota/429 -> auto-swapped to coder_worker (DeepSeek-V4-Pro)"`.

---

## 3. Data Schema: `tasks.json`

The live unit of orchestration, watched by `cao-monitor` and `cao-auto`:

```json
[
  {
    "id": "t1",
    "title": "Build Auth Contract and JWT Validator",
    "detail": "Define AuthServiceInterface in backend/auth/contracts.py and write reference JWT test.",
    "role": "architect",
    "engine": "claude_worker",
    "model": "claude-opus-4-8",
    "fallback_engine": "coder_worker",
    "fallback_model": "deepseek-ai/DeepSeek-V4-Pro",
    "files": ["backend/auth/contracts.py", "tests/test_auth.py"],
    "depends_on": [],
    "status": "pending",
    "created_at": "2026-09-20T20:20:00Z",
    "started_at": null,
    "done_at": null,
    "comments": [],
    "qa": null
  }
]
```

### Status Lifecycle:
* `pending`: Awaiting unsatisfied dependencies or worker capacity.
* `running`: Actively executing in a CAO worker terminal.
* `done`: Finished, file changes verified, worker exited cleanly.
* `blocked`: Failed on 429 (transient, immediately swapped to fallback) or unresolvable error.

---

## 4. The Autonomous Engine (`run/cao-auto`)

`cao-auto` is a standalone Python executable (`run/cao-auto`, symlinked to `~/.local/bin/cao-auto`).

### Core Modules:
1. **`DagScheduler`**: Resolves dependencies (`depends_on`), enforces file lock disjointness (two concurrent tasks cannot modify the same file path), and yields ready tasks up to `max_concurrent_workers`.
2. **`CaoClient`**: Interfaces with CAO Server daemon (`http://127.0.0.1:9889`):
   * `POST /sessions` / `POST /terminals` to launch worker tasks.
   * `GET /terminals/{id}` to poll lifecycle status (`IDLE`, `PROCESSING`, `COMPLETED`, `ERROR`).
   * `DELETE /terminals/{id}` for cleanup.
3. **`QuotaGuard`**: Inspects terminal output for 429 / quota patterns, executes instant swap to `coder_worker`.
4. **`TelegramNotifier`**: Sends structured telemetry via Telegram Bot API when configured.

---

## 5. Autonomous Audit Gate & Self-Healing Loop

When all tasks in `tasks.json` reach `status: "done"`, `cao-auto` triggers the verification pipeline:
1. **Structured Diff Audit (`antigravity_worker`):**
   * Dispatches `antigravity_worker` over all files in `git diff origin/main...HEAD`.
   * Outputs `cao_session/session_NNN/reports/audit.md`.
   * Classifies findings: `[critical]`, `[major]`, `[minor]`.
2. **Automated Test Suite:**
   * Runs project unit/integration tests (`pytest`, `npm test`, or `Makefile`).
   * Runs `cao-aggressive` for security, secrets, and compliance scoring.
3. **Self-Healing Loop:**
   * If any `[critical]` issue or failing test is found (`BLOCKER`):
     * Generates a fix-task `t_fix_<N>`.
     * Assigns to the worker that introduced the code (or `coder_worker` if out of quota).
     * Re-runs the test suite and audit.
     * Loops until 0 blockers remain.
4. **Final Sign-Off:**
   * Sets `qa: {"verdict": "pass", "by": "antigravity_worker", "at": "<iso>", "notes": "0 blockers, tests passing"}` across all tasks.
   * Sends final Telegram completion report.

---

## 6. Telegram Telemetry & Alerting

### Configuration (`~/.config/cao/cao.env` or `.env`):
```env
TELEGRAM_BOT_TOKEN="123456789:ABCDefghIJKlmnoPQRstuvwxYZ"
TELEGRAM_CHAT_ID="-1001234567890"
```

### Notification Events:
| Event | Emoji | Priority | Sample Message |
|---|---|---|---|
| **Session Started** | 🚀 | INFO | `🚀 [session_002] Started 5 tasks on project razmetka` |
| **Model Fallback** | ⚠️ | WARN | `⚠️ [t1] claude_worker hit 429 quota -> auto-swapped to coder_worker (DeepSeek-V4-Pro)` |
| **Audit Blocker** | 🚨 | WARN | `🚨 [Audit] Blocker in AudioAnnotator.jsx: missing bounds check. Auto-dispatching fix-task.` |
| **Session Done** | ✅ | SUCCESS | `✅ [session_002] All 5 tasks completed. Audit PASS (0 blockers). Tests PASS.` |
| **Fatal Blocker** | ❌ | ERROR | `❌ [session_002] Execution halted: all fallback engines exhausted.` |

If `TELEGRAM_BOT_TOKEN` is unset or empty, the notifier logs locally and continues without error.

---

## 7. Supervisor Integration (Zero Extra Steps)

The supervisor prompt (`code_supervisor.md`) is configured so that once the user approves the task list:
1. The supervisor writes `cao_session/session_NNN/tasks.json`.
2. It launches `cao-auto --session session_NNN` in the background.
3. It prints:
   > *"Task list confirmed (X tasks). Autonomous dispatcher is running in background. You can now safely detach (`Ctrl-b d`) and watch live progress via `cao-monitor --watch`."*
4. The user detaches, and Telegram delivers updates to their phone.
