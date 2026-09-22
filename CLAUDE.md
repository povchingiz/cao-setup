# wcao — Multi-Engine Autonomous CLI Agent Orchestrator

> **Note for Claude Code:** This repository adheres to the universal [`AGENTS.md`](file:///Users/yerta/wcao/AGENTS.md) protocol. When the user asks how to run, set up, or test `wcao`, follow the **3-Step Interactive Onboarding Protocol** in `AGENTS.md`.

## Quick Orientation
`wcao` is the management, memory, and orchestration platform for CAO. It renders agent profiles, manages tmux worker daemon sessions, and coordinates autonomous multi-agent engineering workflows.

## Essential Commands
```bash
run/cao-doctor             # Validate system dependencies and worker engines
run/cao-run                # Start interactive supervisor session in tmux
run/cao-auto "<goal>"      # Run headless autonomous DAG execution
./3_apply/apply.sh         # Render prompts/configs and re-register profiles with daemon
uv run --with pytest pytest tests/  # Run orchestrator test suite
run/cao-stop               # Terminate running orchestrator sessions
run/cao-limits             # Inspect provider token and rate limits
run/cao-monitor            # Real-time task board viewer
```

## AI Agent Workspace Standard (One Set of Rules)
1. **Single Home for Agent Artifacts — `wcao/`**:
   - All implementation plans MUST be saved in `wcao/plans/YYYY-MM-DD-<slug>.md` (or updated in `wcao/plans/now.md`).
   - All Mermaid diagrams and architecture blueprints go to `wcao/design/`.
   - Audit findings and stress-test reports go to `wcao/audit/`.
   - DO NOT create scattered files/folders in the root (`NOW.md`, `SESSION_STATE.md`, `cao_session/`, `daily/`, `plans/`).
2. **Session State**:
   - Check `wcao/projectstate.json` and `wcao/plans/now.md` for active tasks.
   - Mark completed items with `[x]` as work progresses.
3. **Configuration Protocol**:
   - Edit worker prompts in `2_configure/prompts/` and settings in `2_configure/cao.config.toml`.
   - Always run `./3_apply/apply.sh` after configuration modifications.
4. **Full Agent Guidance**:
   - See [`AGENTS.md`](file:///Users/yerta/wcao/AGENTS.md) for the complete troubleshooting matrix and onboarding flow.
