# CAO Master Implementation Plan & Prioritized Task List

> **Date:** 2026-09-22  
> **Status:** Active / Prioritized  
> **Reference Specs:**  
> - [`wcao/plans/now.md`](file:///Users/yerta/cao-setup/wcao/plans/now.md)  
> - [`wcao/plans/2026-09-21-hermes-memory-and-engine-expansion.md`](file:///Users/yerta/cao-setup/wcao/plans/2026-09-21-hermes-memory-and-engine-expansion.md)  
> - [`wcao/plans/2026-09-20-autonomous-cao-orchestration.md`](file:///Users/yerta/cao-setup/wcao/plans/2026-09-20-autonomous-cao-orchestration.md)  
> - [`wcao/plans/cao-limits-design.md`](file:///Users/yerta/cao-setup/wcao/plans/cao-limits-design.md)  

---

## 1. Executive Summary

This master plan synthesizes all active development streams into an actionable roadmap:
1. **Foundation & Session Isolation (P0)**: Fix workspace root discovery so background agents (`cao-auto`) operate correctly on `wcao/tasks.json`, and scope supervisor tmux sessions by project to allow parallel instances.
2. **Context & Token Compaction (P1)**: Implement the Hermes 50% window compaction rule to prevent supervisor amnesia and token burn during long runs.
3. **Structured & Procedural Memory (P2)**: Implement auto-generating procedural skills (`wcao/skills/`) from QA fixes and SQLite FTS5 episodic search (`wcao/memory.sqlite`).
4. **Engine Expansion & Hardening (P3)**: Support Nous Hermes CLI worker (`hermes_worker`) and add automated stress/conformance tests.

---

## 2. Priority Matrix

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ Priority 0: Active Foundations & Session Isolation (Prerequisite for background running)   │
│   ├── [ ] P0.1 Fix working_directory root detection in run/cao_auto.py for wcao/tasks.json │
│   ├── [ ] P0.2 Scoped supervisor tmux sessions by project (cao-run --project / dir hash)    │
│   ├── [ ] P0.3 Update cao-stop to support targeting scoped project sessions                │
│   └── [x] P0.4 cao-limits CLI & quota inspector (Built and verified)                       │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Priority 1: Token Efficiency & Context Compaction (Hermes 50% Rule)                         │
│   ├── [ ] P1.1 Turn/Token Estimator hook in cao-run / cao-auto                             │
│   └── [ ] P1.2 State Compactor: compress tool logs to state diff; preserve tasks & design  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Priority 2: Structured & Procedural Memory                                                  │
│   ├── [ ] P2.1 Dynamic Procedural Memory: auto-generate wcao/skills/<topic>.md from QA     │
│   ├── [ ] P2.2 Update agent prompt templates to auto-load wcao/skills/                     │
│   └── [ ] P2.3 SQLite FTS5 Episodic Memory: wcao/memory.sqlite + run/cao-memory CLI        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Priority 3: Engine Expansion & Verification Hardening                                       │
│   ├── [ ] P3.1 Support hermes_worker (Nous Hermes CLI) in render_config.py & prompts       │
│   ├── [ ] P3.2 Conformance Tests: Worker crash recovery and PID restart                    │
│   └── [ ] P3.3 Conformance Tests: Mid-DAG 429 failover and artifact validation             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Tasks Specification

### Priority 0: Foundations & Session Isolation

#### Task P0.1: Fix working_directory root detection in `run/cao_auto.py`
- **ID:** `p0_repo_root_fix`
- **Target Files:** [`run/cao_auto.py`](file:///Users/yerta/cao-setup/run/cao_auto.py), [`tests/test_auto.py`](file:///Users/yerta/cao-setup/tests/test_auto.py)
- **Problem:** `AutonomousRunner._dispatch_task` sets `working_directory=str(self.session_dir.parent.parent)`. When `tasks.json` is located in `wcao/`, `session_dir.parent.parent` resolves to `/Users/yerta` instead of the project directory. Similarly, `_run_audit_gate` checks `self.session_dir.parent.parent`.
- **Solution:** Add helper `find_repo_root(start_dir: Path) -> Path` that searches upwards for `.git`, `pyproject.toml`, or `cao.config.toml`. Use this root for worker launches and audit tests.
- **Verification:** Run unit tests via `PYTHONPATH=. uv run --with pytest pytest tests/test_auto.py`.

#### Task P0.2: Scoped supervisor tmux sessions
- **ID:** `p0_multi_project_sessions`
- **Target Files:** [`run/cao-run`](file:///Users/yerta/cao-setup/run/cao-run), [`run/cao-auto`](file:///Users/yerta/cao-setup/run/cao-auto)
- **Problem:** `cao-run` hardcodes `cao-supervisor` as the tmux session name. Launching CAO in two projects simultaneously fails with `Session 'cao-supervisor' already exists`.
- **Solution:** Allow `--project <name>` or default to `cao-supervisor-$(basename "$PWD")`. Update tmux collision checks and reattachment messages.

#### Task P0.3: Scoped session termination in `cao-stop`
- **ID:** `p0_scoped_cao_stop`
- **Target Files:** [`run/cao-stop`](file:///Users/yerta/cao-setup/run/cao-stop)
- **Solution:** Allow `cao-stop --project <name>` or stop current project session; `cao-stop --all` to kill all project supervisors.

---

### Priority 1: Hermes 50% Context Compactor

#### Task P1.1: Context Turn & Token Usage Estimator
- **ID:** `p1_context_estimator`
- **Target Files:** [`run/cao_compactor.py`](file:///Users/yerta/cao-setup/run/cao_compactor.py), [`tests/test_compactor.py`](file:///Users/yerta/cao-setup/tests/test_compactor.py)
- **Goal:** Track turn count and estimated tokens for active supervisor or agent runs. Trigger when history reaches 50% of model window.

#### Task P1.2: Pre-Emptive State Compactor
- **ID:** `p1_state_compactor`
- **Target Files:** [`run/cao_compactor.py`](file:///Users/yerta/cao-setup/run/cao_compactor.py), [`run/cao_auto.py`](file:///Users/yerta/cao-setup/run/cao_auto.py)
- **Goal:** When 50% threshold is reached:
  - Preserve: active task DAG (`tasks.json`), architecture contract (`wcao/design/`), root objective.
  - Distill: worker command stdout, file listings, and intermediate dialogue into concise summary.
  - Write checkpoint to `wcao/plans/now.md`.

---

### Priority 2: Structured & Procedural Memory

#### Task P2.1: Dynamic Procedural Skills (`wcao/skills/`)
- **ID:** `p2_procedural_skills`
- **Target Files:** [`run/cao_skills.py`](file:///Users/yerta/cao-setup/run/cao_skills.py), [`2_configure/prompts/`](file:///Users/yerta/cao-setup/2_configure/prompts/)
- **Goal:** Enable `antigravity_worker` (QA) to auto-generate `wcao/skills/<topic>.md` when solving unique environment or build bugs. Update prompt templates to instruct agents to read `wcao/skills/*.md`.

#### Task P2.2: SQLite FTS5 Episodic Memory
- **ID:** `p2_sqlite_fts5_memory`
- **Target Files:** [`run/cao_memory.py`](file:///Users/yerta/cao-setup/run/cao_memory.py), [`run/cao-memory`](file:///Users/yerta/cao-setup/run/cao-memory), [`tests/test_memory.py`](file:///Users/yerta/cao-setup/tests/test_memory.py)
- **Goal:** Create `wcao/memory.sqlite` with full-text search indexing (`fts5`) for past architectural decisions, bug fixes, and user preferences. Provide `cao-memory query "<keyword>"`.

---

### Priority 3: Engine Expansion & Hardening

#### Task P3.1: Nous Hermes Worker CLI Integration
- **ID:** `p3_hermes_worker`
- **Target Files:** [`3_apply/render_config.py`](file:///Users/yerta/cao-setup/3_apply/render_config.py), [`run/cao-doctor`](file:///Users/yerta/cao-setup/run/cao-doctor), [`2_configure/cao.config.toml`](file:///Users/yerta/cao-setup/2_configure/cao.config.toml), [`2_configure/prompts/hermes.md`](file:///Users/yerta/cao-setup/2_configure/prompts/hermes.md)
- **Goal:** Support Nous Hermes Agent CLI as a native worker engine for autonomous tasks.

#### Task P3.2: HarnessRouter Conformance & Stress Test Suite
- **ID:** `p3_conformance_suite`
- **Target Files:** [`tests/test_conformance.py`](file:///Users/yerta/cao-setup/tests/test_conformance.py)
- **Goal:** Implement tests for worker crash recovery (re-polling dead tmux PID without hang), mid-DAG 429 quota failover, and task artifact integrity checks.
