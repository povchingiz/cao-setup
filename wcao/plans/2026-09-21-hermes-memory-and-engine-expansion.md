# Implementation Plan: Hermes-Inspired Memory, Skills & Engine Expansion

**Date:** 2026-09-21  
**Status:** Draft / Prioritized  
**Context:** Insights from [NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent) and [HarnessRouter](https://github.com/HarnessRouter/harnessrouter) applied to `cao-setup`.

---

## 1. Executive Summary & Goals

This plan incorporates the best architectural patterns from Hermes Agent and HarnessRouter into CAO:
1. **Prevent Token Burn & Context Amnesia**: Introduce a 50% threshold context compactor for the supervisor.
2. **Procedural Memory (Dynamic Skills)**: Allow agents to record and inherit repo-specific lessons in `wcao/skills/`.
3. **Episodic SQLite FTS5 Memory**: Replace slow text scans with instant full-text indexed memory recall.
4. **Engine Expansion**: Support `hermes_worker` as an open-source autonomous agent engine.
5. **Stress Verification**: Port HarnessRouter's failover and sandbox recycle scenarios into `tests/`.

---

## 2. Priority Matrix & Roadmap

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Priority 0: Immediate Foundations (In Progress)                           │
│   ├── Multi-Project Sessions (tmux scoping by repo)                       │
│   └── cao-limits (real-time quota & rate-limit monitoring)                │
├───────────────────────────────────────────────────────────────────────────┤
│ Priority 1: High-ROI Token & Quality Optimizations (Immediate Next)       │
│   ├── Pre-emptive Context Compaction (50% window rule for supervisor)     │
│   └── Dynamic Procedural Memory (wcao/skills/ auto-skill generation)      │
├───────────────────────────────────────────────────────────────────────────┤
│ Priority 2: Structured Memory Infrastructure                              │
│   └── SQLite FTS5 Episodic Memory Layer (wcao/memory.sqlite)              │
├───────────────────────────────────────────────────────────────────────────┤
│ Priority 3: Engine Expansion & Verification Hardening                     │
│   ├── hermes_worker integration (Nous Hermes CLI provider)                │
│   └── Conformance & Recycle Stress Tests in tests/                        │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Specifications by Priority

### P0 — Immediate Foundations (Active)
* **P0.1: Multi-Project Sessions & Scoped Names**:
  - Automatically append directory basename or hash to supervisor tmux sessions (`cao-supervisor-<project>`).
  - Eliminate collision when working on multiple repositories simultaneously.
* **P0.2: `cao-limits` Quota Inspector**:
  - Implement `run/cao-limits` to poll remaining quota on Claude, Codex, Gemini/AGY, and local endpoints.

---

### P1 — High-ROI Hermes Patterns (Next Sprint)

#### P1.1: Pre-Emptive Context Compactor (The 50% Rule)
* **Problem**: As supervisor sessions run, conversational history accumulates thousands of tokens of raw tool output, file dumps, and status polling, degrading reasoning and burning quota.
* **Hermes Solution**: When context estimates exceed 50% of the active context window, run a compactor.
* **CAO Implementation**:
  - Hook in `run/cao-auto` and `run/cao-run` tracking turn count / token usage.
  - When threshold is hit, invoke a lightweight compaction step:
    - **Retain**: Root goal, current task DAG (`tasks.json`), architecture contract (`wcao/design/`).
    - **Compress**: Intermediate worker outputs, terminal stdout, verbose file listings into a concise state diff.
  - Update `wcao/plans/now.md` with compacted state.

#### P1.2: Dynamic Procedural Memory (`wcao/skills/`)
* **Problem**: Lessons learned during a task (e.g. "always use `--experimental-strip-types` with Node 22", or "this repo requires `poetry run pytest`") currently stay in raw terminal logs or static prompts.
* **Hermes Solution**: Auto-generating `SKILL.md` files representing repeatable workflows.
* **CAO Implementation**:
  - Create directory: `wcao/skills/`.
  - When `antigravity_worker` (QA) solves an obscure error or verifies a tricky fix, have it write a structured markdown file: `wcao/skills/<topic>.md`.
  - Supervisor and workers are instructed in their prompts to check `wcao/skills/*.md` before executing new tasks.
  - Avoid touching static prompts in `2_configure/prompts/`.

---

### P2 — SQLite FTS5 Episodic Memory (Medium Term)

* **Problem**: MCP memory tools (`memory_store`, `memory_recall`) rely on in-memory buffers or flat files, which do not scale across dozens of historical sessions.
* **Hermes Solution**: SQLite FTS5 full-text search table storing episodic memories, indexed by tags, file paths, and timestamps.
* **CAO Implementation**:
  - Create `wcao/memory.sqlite`.
  - Schema:
    ```sql
    CREATE VIRTUAL TABLE IF NOT EXISTS session_memory USING fts5(
        session_id,
        category,      -- 'bug_fix', 'architecture', 'user_preference', 'dependency'
        summary,
        details,
        file_paths,
        created_at
    );
    ```
  - Provide a fast CLI helper: `run/cao-memory query "auth middleware"` to quickly retrieve past learnings during planning.

---

### P3 — Engine Expansion & Conformance Hardening (Longer Term)

#### P3.1: `hermes_worker` Engine Integration
* **Goal**: Support Nous Hermes Agent CLI as an open-source alternative for reasoning and self-learning.
* **Steps**:
  1. Add `hermes_cli` to `KNOWN_PROVIDERS` in `3_apply/render_config.py`.
  2. Map `hermes` in `run/cao-doctor` and `1_install/bootstrap.sh`.
  3. Define `[workers.hermes_worker]` in `2_configure/cao.config.toml`.
  4. Create `2_configure/prompts/hermes.md`.

#### P3.2: HarnessRouter-Style Stress & Conformance Tests
* **Scenarios to add in `tests/`**:
  1. **Worker Crash & Session Recovery**: Abruptly kill a worker tmux session and ensure `cao-auto` / supervisor detects the dead PID and retries without deadlocking.
  2. **Supervisor Quota Exhaustion Mid-DAG**: Simulate a 429 quota error mid-execution and verify supervisor state seamlessly migrates to `antigravity_cli` or `codex`.
  3. **Artifact Integrity Check**: Verify all declared task outputs actually exist on disk and pass syntax checks before marking a task complete.
