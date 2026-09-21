# Autonomous CAO Orchestration & Self-Healing Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless autonomous execution engine (`cao-auto`) for CAO with universal OpenCode 429 auto-fallback, real-time Telegram telemetry, and an automated self-healing Audit Gate.

**Architecture:** A Python-based autonomous orchestrator (`run/cao_auto.py` + CLI `run/cao-auto`) that reads `tasks.json`, schedules parallel tasks based on a dependency DAG and file disjointness, manages CAO worker terminals via the local CAO daemon REST API, auto-swaps to `coder_worker` on 429 limits, emits alerts to Telegram, and triggers `antigravity_worker` + test suites on completion.

**Tech Stack:** Python 3.11+ (`urllib`, `dataclasses`, `json`, `subprocess`), CAO REST API (port 9889), Telegram Bot API.

**Spec:** [`docs/superpowers/specs/2026-09-20-autonomous-cao-orchestration-design.md`](file:///Users/yerta/cao-setup/docs/superpowers/specs/2026-09-20-autonomous-cao-orchestration-design.md)

## Global Constraints
- Must not require external PyPI dependencies beyond Python standard library (keeps `cao-auto` fast and dependency-free).
- Graceful degradation: if Telegram credentials are not set, it must log locally and continue without error.
- All live task updates MUST write directly to `cao_session/session_NNN/tasks.json` so `cao-monitor` can watch in real time.
- Universal fallback MUST target `coder_worker` with model `deepseek-ai/DeepSeek-V4-Pro` (from Nitec local endpoint).

---

### Task 1: Telegram Telemetry Module

**Files:**
- Create: `run/cao_telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Consumes: `os.environ` / `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- Produces: `notify_telegram(text: str, level: str = "info") -> bool`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/test_telegram.py
from unittest.mock import patch, MagicMock
from run.cao_telegram import notify_telegram

def test_telegram_skipped_when_no_token():
    with patch.dict("os.environ", {}, clear=True):
        assert notify_telegram("test message") is False

def test_telegram_sends_when_configured():
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "999"}):
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_open.return_value.__enter__.return_value = mock_resp
            assert notify_telegram("test message", level="warn") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram.py`
Expected: FAIL (module `run.cao_telegram` not found).

- [ ] **Step 3: Implement `run/cao_telegram.py`**

```python
# run/cao_telegram.py
import json
import os
import sys
import urllib.request
import urllib.error

ICONS = {
    "info": "ℹ️",
    "warn": "⚠️",
    "block": "🚨",
    "success": "✅",
    "error": "❌",
}

def notify_telegram(text: str, level: str = "info") -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    icon = ICONS.get(level.lower(), "ℹ️")
    formatted = f"{icon} {text}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": formatted, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"WARN: Telegram notification failed: {exc}", file=sys.stderr)
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add run/cao_telegram.py tests/test_telegram.py
git commit -m "feat(telemetry): add telegram notification helper with zero external dependencies"
```

---

### Task 2: Quota & 429 Fallback Engine

**Files:**
- Create: `run/cao_fallback.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Consumes: Task dictionary from `tasks.json`
- Produces: `is_quota_error(text: str) -> bool`, `apply_fallback(task: dict, error_reason: str) -> dict`

- [ ] **Step 1: Write failing unit test**

```python
# tests/test_fallback.py
from run.cao_fallback import is_quota_error, apply_fallback

def test_is_quota_error():
    assert is_quota_error("Error 429: rate limit exceeded") is True
    assert is_quota_error("quota exceeded for current billing window") is True
    assert is_quota_error("usage limit reached") is True
    assert is_quota_error("SyntaxError: invalid syntax") is False

def test_apply_fallback():
    task = {
        "id": "t1",
        "engine": "claude_worker",
        "model": "claude-opus-4-8",
        "fallback_engine": "coder_worker",
        "fallback_model": "deepseek-ai/DeepSeek-V4-Pro",
        "comments": []
    }
    updated = apply_fallback(task, "rate limit 429")
    assert updated["engine"] == "coder_worker"
    assert updated["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert len(updated["comments"]) == 1
    assert "auto-swapped" in updated["comments"][0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fallback.py`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `run/cao_fallback.py`**

```python
# run/cao_fallback.py
import re
from datetime import datetime, timezone

QUOTA_PATTERNS = [
    r"429",
    r"rate\s*limit",
    r"quota\s*exceeded",
    r"usage\s*limit",
    r"insufficient\s*credits",
    r"credit\s*balance",
    r"overloaded",
]

def is_quota_error(text: str) -> bool:
    if not text:
        return False
    return any(re.search(pat, text, re.IGNORECASE) for pat in QUOTA_PATTERNS)

def apply_fallback(task: dict, reason: str = "quota/429") -> dict:
    prev_engine = task.get("engine", "unknown")
    fallback_eng = task.get("fallback_engine", "coder_worker")
    fallback_mod = task.get("fallback_model", "deepseek-ai/DeepSeek-V4-Pro")

    task["engine"] = fallback_eng
    task["model"] = fallback_mod

    comments = task.setdefault("comments", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    comment = {
        "by": "orchestrator",
        "at": now_iso,
        "text": f"Tier 1 limit on {prev_engine} ({reason}) -> auto-swapped to {fallback_eng} ({fallback_mod})"
    }
    comments.append(comment)
    return task
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fallback.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add run/cao_fallback.py tests/test_fallback.py
git commit -m "feat(fallback): add quota error detection and universal fallback applicator"
```

---

### Task 3: Autonomous DAG Dispatcher Core (`run/cao_auto.py`)

**Files:**
- Create: `run/cao_auto.py`
- Test: `tests/test_auto.py`

**Interfaces:**
- Consumes: `cao_session/session_NNN/tasks.json`
- Produces: `DagScheduler`, `CaoDaemonClient`, `run_autonomous_session(session_dir: Path)`

- [ ] **Step 1: Write failing unit test for DAG scheduling and file collision**

```python
# tests/test_auto.py
from run.cao_auto import DagScheduler

def test_dag_scheduler_ready_tasks():
    tasks = [
        {"id": "t1", "status": "pending", "depends_on": [], "files": ["a.py"]},
        {"id": "t2", "status": "pending", "depends_on": ["t1"], "files": ["b.py"]},
        {"id": "t3", "status": "pending", "depends_on": [], "files": ["a.py"]}, # touches a.py -> conflicts with t1
    ]
    scheduler = DagScheduler(tasks)
    ready = scheduler.get_ready_tasks(running_files=set())
    # t1 is ready. t2 blocked on t1. t3 collides with t1 on a.py.
    assert [t["id"] for t in ready] == ["t1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto.py`
Expected: FAIL

- [ ] **Step 3: Implement `run/cao_auto.py`**

Implement `DagScheduler` (DAG dependency check + disjoint file sets), `CaoDaemonClient` (HTTP calls to `127.0.0.1:9889` for `/terminals` creation/status polling), and the main execution loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auto.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add run/cao_auto.py tests/test_auto.py
git commit -m "feat(auto): implement DAG scheduler and CAO daemon orchestrator loop"
```

---

### Task 4: CLI Executable & Autonomous Audit Gate (`run/cao-auto`)

**Files:**
- Create: `run/cao-auto`
- Test: `tests/test_audit_gate.py`

**Interfaces:**
- Consumes: CLI args `--session <name>`, `--dir <path>`, `--dry-run`
- Produces: Executable binary that runs execution DAG, triggers `antigravity_worker` audit, runs `pytest`/`cao-aggressive`, and self-heals blockers.

- [ ] **Step 1: Write failing test for audit blocker remediation**
- [ ] **Step 2: Implement Audit Gate handler in `run/cao_auto.py` and CLI script in `run/cao-auto`**
- [ ] **Step 3: Test CLI with `--dry-run` and mock session**
- [ ] **Step 4: Commit**

```bash
git add run/cao-auto tests/test_audit_gate.py
git commit -m "feat(cli): add cao-auto executable with automated audit gate and self-healing"
```

---

### Task 5: Integration, Bootstrap Symlinks & Apply Hook

**Files:**
- Modify: `1_install/bootstrap.sh` (symlink `cao-auto`)
- Modify: `run/cao-doctor` (add check for `cao-auto`)
- Modify: `3_apply/apply.sh`
- Modify: `NOW.md`

- [ ] **Step 1: Add symlink in `1_install/bootstrap.sh`**
- [ ] **Step 2: Add freshness check in `run/cao-doctor`**
- [ ] **Step 3: Run `cao-doctor` and test suite (`pytest`)**
- [ ] **Step 4: Commit and push**
