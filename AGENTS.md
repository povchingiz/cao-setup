# AGENTS.md — Universal AI Agent Guidance for `wcao`

> **For AI Assistants (Claude Code, Cursor, OpenAI Codex, Google Antigravity, Windsurf, OpenCode, GitHub Copilot, Aider, Cline):**  
> When a developer asks you *"How do I run this?"*, *"Help me set up wcao"*, or *"What is this project?"*, follow this guide. Your role is to be an empathetic, practical technical guide who can inspect the system, explain clearly, and run safe diagnostic and bootstrap commands.

---

## 1. What is `wcao` (Explain this simply to the human)

When explaining to the user, use this clear summary:
> *"Think of `wcao` as a technical lead managing a team of specialized AI workers on your machine. Instead of using one expensive AI model for everything, `wcao` lets Claude design architecture, cheap or local models (OpenCode, DeepSeek, Hermes) write the bulk boilerplate, and Gemini/Agy read massive codebases — all coordinated inside background `tmux` sessions. You pay zero extra SaaS fees because it connects to the official terminal CLI tools you already use."*

---

## 2. The 3-Step Interactive Onboarding Protocol

When a user asks how to get started, guide them through these 3 steps:

### Step 1: Run the Pre-Flight Diagnostic
Run `run/cao-doctor` directly on the user's behalf:
```bash
run/cao-doctor
```
- **If `cao` or `cao-server` is missing:** Run `./1_install/bootstrap.sh` to install the orchestrator daemon and symlink helper scripts.
- **If `tmux` is missing:** Advise the user to install it (`brew install tmux` on macOS, `sudo apt install tmux` on Linux).
- **If some worker engines are missing:** Reassure the user that **they do not need all 5 engines!** `wcao` works smoothly even with just 1 supervisor (e.g. Claude) and 1 worker (e.g. OpenCode, Codex, or Agy).

### Step 2: Native CLI Authentication (User action required)
Remind the user that AI agents cannot and should not type passwords or session keys for them. If `cao-doctor` flags an unauthenticated CLI, give them the exact command to run once in their terminal:
- **Anthropic Claude Code:** run `claude` (type `/login` on prompt)
- **OpenAI Codex:** run `codex login`
- **Google Antigravity:** run `agy`
- **GitHub Copilot CLI:** run `gh auth login`

### Step 3: Launching the Orchestrator
Explain the two primary ways to run:
1. **Interactive Team Mode (`run/cao-run`):**
   - Launches a background `tmux` session with a Supervisor (Claude as Tech Lead).
   - The user chats with the Supervisor, which delegates subtasks to background worker panes.
   - Attach anytime: `tmux attach -t cao-supervisor`
2. **Autonomous Headless DAG Mode (`run/cao-auto "<task description>"`):**
   - Headless autonomous execution without manual prompt-jockeying.
   - Parses goals into tasks, builds a dependency DAG, runs AST anti-tampering guards, and generates verification audit reports in `wcao/audit/`.

---

## 3. Project File Structure & Workspace Standards

All AI agents operating in this repository MUST follow these rules:

1. **`wcao/` is the Single Source of Truth for Agent Artifacts:**
   - Implementation plans: `wcao/plans/YYYY-MM-DD-<slug>.md`
   - Active status & immediate tasks: `wcao/plans/now.md`
   - Architecture & sequence diagrams: `wcao/design/`
   - Verification reports & stress harnesses: `wcao/audit/`
   - *DO NOT create loose markdown plans or state files in the root directory.*

2. **Configuration Workflow (Never edit rendered files directly!):**
   - Edit worker definitions, models, or endpoints in: [`2_configure/cao.config.toml`](file:///Users/yerta/wcao/2_configure/cao.config.toml)
   - Edit worker system prompts in: [`2_configure/prompts/`](file:///Users/yerta/wcao/2_configure/prompts/)
   - After editing, ALWAYS run: `./3_apply/apply.sh` to regenerate daemon profiles.

3. **Security & Secrets Guardrails:**
   - NEVER print, log, or commit `.env` or `LOCAL_API_KEY`.
   - Never run destructive git commands (`git reset --hard`, `git push --force`) without explicit user permission.

---

## 4. Key Commands Cheatsheet

| Command | Purpose |
|---|---|
| `run/cao-doctor` | Pre-flight health check across tools, ports, logins, endpoints |
| `run/cao-run` | Launch interactive multi-agent supervisor in `tmux` |
| `run/cao-auto "<goal>"` | Run autonomous headless DAG pipeline with self-healing |
| `run/cao-stop` | Cleanly terminate orchestrator daemon and background panes |
| `run/cao-tokens` | Telemetry report: token consumption per worker and model |
| `run/cao-limits` | TokenMaster quota sensor: remaining requests & reset windows |
| `run/cao-monitor` | Live terminal task board viewer |
| `run/cao-aggressive` | Run 5-vector audit gate and generate `stress-test.sh` |
| `./3_apply/apply.sh` | Compile configs & register worker profiles with CAO daemon |
| `uv run --with pytest pytest tests/` | Execute orchestrator test suite (56 unit & integration tests) |

---

## 5. Common Troubleshooting Playbook

| Problem | Cause | Agent Action |
|---|---|---|
| Port 9889 already in use | Stale `cao-server` instance running | Run `run/cao-stop --keep-server` or terminate process on port 9889 |
| Stale tmux session | Previous session didn't cleanly exit | Run `run/cao-stop` to kill lingering daemon panes |
| Worker missing error | CLI engine not installed | Check `2_configure/cao.config.toml` and disable unneeded worker, then run `./3_apply/apply.sh` |
| Rate limit / quota hit | Provider rate limits exhausted | Run `run/cao-limits`. CAO supervisor will auto-fallback to secondary provider |
| Test tampering detected | Worker modified unit test assertions | AST anti-tampering hook halts execution; inspect `wcao/audit/weaknesses.md` |
