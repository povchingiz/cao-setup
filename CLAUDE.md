# cao-setup — Provisioner & Configuration Layer for CLI Agent Orchestrator (CAO)

## What this is
`cao-setup` is the management and prompt configuration repo for CAO. It renders agent profiles, manages tmux worker daemon sessions, and orchestrates multi-agent coding workflows.

## Commands
```bash
./3_apply/apply.sh         # Render prompts/configs and re-register profiles with daemon
pytest tests/              # Run orchestrator unit and integration tests
run/cao-doctor             # Validate system dependencies and worker engines
run/cao-run                # Start interactive supervisor session
run/cao-auto               # Run headless autonomous DAG execution
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
