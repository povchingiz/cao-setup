# CAO — system map (what exists, what's wired, what's a gap)

Detailed sequence diagram: [`cao-architecture.mmd`](./cao-architecture.mmd) (render with mermaid; also viewable in any Mermaid viewer / GitHub).

This file is the human index to that diagram — the three phases, the files each touches, and the known gaps.

## The three phases

| Phase | Trigger | Entry point | What it does |
|-------|---------|-------------|--------------|
| **1. Install** | once, on a fresh machine | `1_install/bootstrap.sh` | prereqs → CAO → worker CLIs → copy prompts → `cao install` → patches → prints login steps |
| **2. Apply** | after editing config/prompts | `3_apply/apply.sh` | `render_config.py` → write live configs → `cao install` each profile → offer server restart |
| **3. Runtime** | each work session | `run/cao-run` | doctor pre-flight → pick supervisor provider → start daemon → `cao launch` supervisor → orchestrate workers |

## Config flow (single source of truth → generated targets)

```
2_configure/cao.config.local.toml   (gitignored, YOUR real endpoint+models+roles)
        │  (falls back to cao.config.toml template if local absent)
        ▼  render_config.py
   ├── ~/.config/cao/settings.json           (orchestrator block)
   ├── ~/.aws/opencode/opencode.json         (nitec endpoint + 3 models)
   └── agent_store/*.md  (STAGING)           (worker frontmatter + supervisor mapping)
        │  cao install
        ▼
   agent-store/*.md  (CANONICAL, cao DB)     (what cao actually launches)
```

## Roles (org structure, after this session's rework)

| Profile | Engine / model | Role | Aliases |
|---------|---------------|------|---------|
| `code_supervisor` | claude | Tech Lead — architecture, coordination, contracts | (supervisor) |
| `claude_worker` | claude | Senior Eng — contracts, hard logic, tricky fixes | claude, architect |
| `coder_worker` | opencode / nitec deepseek | Coding — impl against blueprint, bulk, CRUD | coder, code, bulk |
| `analyst_worker` | antigravity (Gemini) | Context Analyst — repo maps, long docs, multimodal | analyst, context, research, map |
| `codex_worker` | codex | Frontend — React/CSS/UI | codex, frontend, ui |
| `antigravity_worker` | antigravity (Gemini) | QA — tests, security, audit | qa, tests, review, audit |

Models in endpoint but **not yet assigned to a worker**: `moonshotai/Kimi-K3`, `zai-org/GLM-5.2-FP8` (available for a future long-context / fallback worker).

## Resilience wired this session

- **Supervisor fallback** (`cao-run` + `cao-doctor`): Claude quota/login dies → env `CAO_SUPERVISOR_PROVIDER` > `~/.cao/supervisor_provider` hint > `claude_code`; launch-fail auto-retries once on antigravity/codex. See [[cao-supervisor-fallback]].
- **Token visibility** (`cao-tokens`): `--daily`, `--heatmap`, `--cao-only`, `--day`. Default counts ALL claude sessions; `--cao-only` isolates cao. See [[cao-tokens-scope]].

## Known gaps / to fix

| Gap | Where | Fix |
|-----|-------|-----|
| **Two stores.** render writes `agent_store` (_, staging); cao uses `agent-store` (-, canonical). Rename/remove of a worker leaves a ghost in the canonical store + cao DB. | `render_config.py:97` LIVE_STORE, cao internals | `prune_stale_profiles` cleans staging only. A rename also needs `cao profile remove <old> -y`. **Consider:** have apply.sh reconcile cao DB against the register list. |
| **kimi/glm idle.** In endpoint, no worker uses them. | `cao.config.local.toml` [endpoint] | Add a `longctx_worker` or fallback wiring when needed. |
| **MCP not inherited.** lean-ctx/symdex are in `~/.claude.json` but workers only have `cao-mcp-server`. | `inherit_mcp.py` (not yet run) | Run `python3 3_apply/inherit_mcp.py --dry-run` then apply. Skills (superpowers) are Claude-Code-only — can't port to codex/agy. |
| **Claude quota not pre-checkable.** `claude auth status` shows login, not quota. | inherent | Real quota only surfaces at launch → cao-run's launch-fail retry covers it. |
