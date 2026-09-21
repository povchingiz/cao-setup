# now.md — cao-setup progress & immediate tasks

> **Branch:** `master`  
> **Status:** Clean  
> **Active Plan:** Multi-Project Sessions & CAO v2 `cao-limits`

---

## What was completed
- [x] Milestone 1–4: Core provisioner, prompt renderer, MCP inheritance, tmux lifecycle.
- [x] Milestone 5: `cao-auto` autonomous DAG dispatcher, Telegram telemetry, universal 429 quota fallback engine.
- [x] Unified `wcao/` workspace standard across runner scripts (`cao-monitor`, `cao-auto`, `cao-aggressive`) and prompt templates.

---

## Immediate Next Tasks

### Milestone 7: Multi-Project Sessions & Scoped Supervisor Names
- [ ] Allow running separate CAO supervisor sessions in different projects simultaneously without tmux collisions (`cao-run --project <name>` or auto-inferring directory basename).
- [ ] Supervisor name scoping in tmux sessions.

### CAO v2: `cao-limits` (Step 1)
- [ ] Build `run/cao-limits` CLI to query rate limits and remaining quotas across engines (Claude, Gemini, Codex, local OpenCode).
- [ ] Expose remaining tokens/requests in status header.
