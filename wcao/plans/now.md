# now.md — cao-setup progress & immediate tasks

> **Branch:** `master`  
> **Status:** Clean  
> **Active Plan:** [`master-plan.md`](master-plan.md)  
> **Autonomous Queue:** [`wcao/tasks.json`](../tasks.json)  

---

## What was completed
- [x] Milestone 1–4: Core provisioner, prompt renderer, MCP inheritance, tmux lifecycle.
- [x] Milestone 5: `cao-auto` autonomous DAG dispatcher, Telegram telemetry, universal 429 fallback engine.
- [x] Unified `wcao/` workspace standard across runner scripts and prompt templates.
- [x] **CAO v2 `cao-limits`**: Completed CLI in [`run/cao-limits`](../../run/cao-limits) & [`run/cao_limits.py`](../../run/cao_limits.py) with visual utilization bars and token spend across Claude, Codex, and OpenCode (17/17 tests passing).
- [x] **Repo Root & Session Isolation (P0)**:
  - [x] Fixed `working_directory` and `root_dir` resolution with `find_repo_root` helper in [`run/cao_auto.py`](../../run/cao_auto.py).
  - [x] Scoped supervisor tmux sessions by project (`cao-supervisor-<project>`) in [`run/cao-run`](../../run/cao-run).
  - [x] Scoped supervisor termination with `--project <name>` and `--all` in [`run/cao-stop`](../../run/cao-stop).
  - [x] Added `pythonpath = ["."]` in [`pyproject.toml`](../../pyproject.toml).
- [x] **Context & Token Compaction (P1 - Hermes 50% Rule)**:
  - [x] Built `ContextCompactor` in [`run/cao_compactor.py`](../../run/cao_compactor.py) and verified with [`tests/test_compactor.py`](../../tests/test_compactor.py).
  - [x] Integrated compactor checkpointing hook into `AutonomousRunner` in [`run/cao_auto.py`](../../run/cao_auto.py).
- [x] **Structured & Procedural Memory (P2)**:
  - [x] Dynamic procedural memory manager in [`run/cao_skills.py`](../../run/cao_skills.py) saving to `wcao/skills/`.
  - [x] Updated agent prompt templates ([`coder_worker.md`](../../2_configure/prompts/coder_worker.md), [`code_supervisor.md`](../../2_configure/prompts/code_supervisor.md)) to check `wcao/skills/*.md`.
  - [x] SQLite FTS5 episodic memory layer in [`run/cao_memory.py`](../../run/cao_memory.py) and CLI [`run/cao-memory`](../../run/cao-memory).
- [x] **Engine Expansion & Conformance Hardening (P3)**:
  - [x] Added `hermes_cli` and `hermes_worker` in [`3_apply/render_config.py`](../../3_apply/render_config.py), [`run/cao-doctor`](../../run/cao-doctor), [`2_configure/cao.config.toml`](../../2_configure/cao.config.toml), and prompts ([`hermes_worker.md`](../../2_configure/prompts/hermes_worker.md)).
  - [x] Added HarnessRouter-inspired crash recovery and mid-DAG 429 failover test suite in [`tests/test_conformance.py`](../../tests/test_conformance.py).
- [x] **Proactive Token-Master Loop (P4)**:
  - [x] Implemented `TokenMaster` in [`run/cao_token_master.py`](../../run/cao_token_master.py) reading live Claude quota window utilization via `cao_limits`.
  - [x] Wired proactive model swapping (>=80% utilization or blocked) to `hermes_worker` / `coder_worker` before hitting rate limits.
  - [x] Added large context & multi-file advisory routing in `_dispatch_task` in [`run/cao_auto.py`](../../run/cao_auto.py).
  - [x] Verified with 6 unit/integration tests in [`tests/test_token_master.py`](../../tests/test_token_master.py) (41/41 test suite passing).
- [x] **Bulletproof Autonomous Engineering Fixes (P5)**:
  - [x] **Autonomous Goal Decomposer (`cao-plan`)**: Built [`run/cao_plan.py`](../../run/cao_plan.py) and [`run/cao-plan`](../../run/cao-plan) generating cycle-free DAGs in `wcao/tasks.json` with TokenMaster routing (7/7 tests passing in [`tests/test_plan.py`](../../tests/test_plan.py)).
  - [x] **Anti-Test-Tampering Gate**: Built [`run/cao_tamper.py`](../../run/cao_tamper.py) detecting weakened assertions or deleted test functions during self-healing, automatically reverting test regressions (4/4 tests passing in [`tests/test_tamper.py`](../../tests/test_tamper.py)).
  - [x] **Architect Escalation Protocol**: Wired self-healing attempt 2+ in [`run/cao_auto.py`](../../run/cao_auto.py) to escalate from `coder_worker` to `hermes_worker` / `claude_worker` for deep root-cause diagnosis.
  - [x] All 56/56 tests passing cleanly.

---

## Prioritized Task Queue

*All items from [`wcao/tasks.json`](../tasks.json) are complete and verified.*
