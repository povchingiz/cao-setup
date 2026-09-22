# CAO — Autonomous CLI Agent Orchestrator

> **Orchestrate your frontier AI coding CLI engines into a cohesive, self-learning engineering squad.**

---

### The Problem
* **Siloed CLI Agents:** Claude Code, Codex, Antigravity/Gemini, OpenCode, and Hermes each live in isolated terminal windows with no shared memory, contracts, or task delegation.
* **Token & Quota Burn:** Using expensive frontier models for mundane boilerplate, migrations, or whole-repo reading exhausts rate limits and quotas rapidly.
* **Context Decay & Amnesia:** As agent sessions grow, token context degrades, leading to hallucinated edits, broken syntax, and forgotten lessons across sessions.
* **Race Conditions in Multi-Agent Coding:** Running multiple autonomous agents simultaneously on the same codebase leads to file collisions and overwritten code.
* **Premature Completion without Verification:** Most agent setups stop as soon as code is written—without running tests, verifying AST syntax, or fixing their own regressions.

---

### The Solution: A Unified Engineering Squad
**CAO (CLI Agent Orchestrator)** turns individual CLI tools into an autonomous, fault-tolerant software engineering system:

* **Tech Lead Supervisor (Claude / AGY):** Plans architecture, decomposes requirements into Directed Acyclic Graphs (DAGs), and delegates.
* **Specialist Workforce:** Routes tasks to the best-fit engine—Claude for hard domain logic, high-throughput models (DeepSeek/OpenCode) for bulk typing, Gemini/AGY for massive-context codebase analysis, Codex for UI, and Hermes for open-source reasoning.
* **Deterministic Execution & Safety Locks:** A headless execution engine (`cao_auto`) schedules tasks, enforces file-level disjointness locks, and prevents parallel collision.
* **Autonomous Closed-Loop Quality:** An aggressive postflight audit gate tests and scans code before marking any task complete, with an automatic self-healing loop that fixes failures without human intervention.
* **Hermes Cross-Engine Memory:** Context compactor (Hermes 50% rule) prevents token blowout, while SQLite FTS5 episodic memory stores lessons learned so future workers never repeat past mistakes.

---

### Core Capabilities at a Glance

| Capability | How CAO Delivers It |
|---|---|
| **Multi-Engine Swarm** | Unifies Claude, Codex, OpenCode, Antigravity, Copilot, and Hermes into one orchestrated pipeline. |
| **Token-Aware Efficiency** | Proactive TokenMaster quota monitoring, automatic high-utilization model swaps, context-size advisories, and 50% window compaction. |
| **Zero-Collision Concurrency** | Task DAG scheduler evaluates dependencies and locks files dynamically across parallel workers. |
| **Autonomous Self-Healing** | Postflight AST checks, security audits, and test suites trigger automatic remediation loops when regressions occur. |
| **Persistent Project Brain (`wcao/`)** | Single source of truth for architectural diagrams (`design/*.mmd`), active plans (`now.md`), and reusable skills (`skills/`). |
| **Quota Resilience** | Real-time detection of 429 rate limits with automatic fallback to secondary engines and supervisor failover. |

---

```
cao-run  →  supervisor (Claude, Tech Lead)  →  assign  →
    ┌ claude_worker       claude       architecture, contracts, hard logic
    ├ coder_worker        opencode     implementation, schemas, CRUD (cheap model)
    ├ analyst_worker      gemini/agy   whole-repo maps, long docs, multimodal (huge context)
    ├ codex_worker        codex        frontend / UI
    ├ antigravity_worker  gemini/agy   QA, tests, security review
    ├ hermes_worker       hermes       open-source reasoning, autonomous implementation
    └ copilot_worker      copilot      general coding hand (role TBD)
```

**Why it saves tokens:** the expensive model (Claude) is spent only on design,
contracts, and coordination. Reading a big repo goes to the huge-context analyst;
the bulk of the typing goes to a cheap coding model against Claude's blueprint.
`cao-tokens` shows you exactly where the tokens went (per day, or cao-only).

**Fault-tolerant by default:** if Claude's quota or login is down, the supervisor
falls back to another engine automatically — `cao-run` never dead-ends (see
*Supervisor fallback*).

Roles above are the **defaults** — every one is editable (see *Configure*).

> **Windows:** not supported natively (CAO needs tmux + POSIX ptys). Use WSL2 —
> see [WINDOWS.md](WINDOWS.md). Inside WSL these steps apply unchanged, if the
> repo lives in your WSL home (not `/mnt/c`).

## Repo layout — by lifecycle phase

```
wcao/          plans/ · design/ · skills/ · audit/ · tasks.json  ← project state, contracts, & memory
1_install/     bootstrap.sh · bootstrap.ps1 · patch_pyte.py     ← run once
2_configure/   cao.config.toml · prompts/*.md                   ← edit these
3_apply/       apply.sh · render_config.py · inherit_mcp.py · inherit_all.py   ← push edits · share MCP
run/           cao-run · cao_auto.py · cao-doctor · cao-stop · cao-memory · cao-aggressive · cao-tokens · cao-plugins
.generated/    settings.json · opencode.json    ← auto-written locally (gitignored)
```

Edit only in `2_configure/`. Everything else is machinery. Never edit the live
files under `~/.aws` or `~/.config` directly — they are generated.

## Command cheatsheet

Every command takes `-h`/`--help`. Nothing here needs arguments to start.

| Command | What it does |
|---------|--------------|
| `cao-run` | health-check, then launch the interactive supervisor in tmux (add `--skip-check` to skip gate) |
| `cao-plan "<goal>"` | **Autonomous Goal Decomposer**: splits high-level goal into acyclic DAG (`wcao/tasks.json`) with TokenMaster routing |
| `python run/cao_auto.py --tasks <path>` | **Headless autonomous runner**: executes task DAG, prevents file race collisions, auto-switches 429 quota, self-heals |
| `cao-memory` | **Episodic memory**: SQLite FTS5 store, recall, and list cross-session lessons (`store`, `recall`, `list`) |
| `cao-aggressive` | **Postflight audit gate**: AST syntax verification, security scan, and test suite execution |
| `cao-doctor` | run pre-flight health check on its own (toolchain, engines, logins, endpoint) |
| `cao-tokens` | heatmap + per-day usage across **all engines**, last 7 days, cao-only (cells are in/out) |
| `cao-plugins` | share Claude MCP + plugins/skills with every engine (`list`, `broadcast --dry-run`) |
| `cao-stop` | end session: stop daemon + tmux sessions (`--workers` keeps supervisor, `-k` keeps daemon) |
| `./3_apply/apply.sh` | push `2_configure/` edits live (renders config, re-registers, offers restart) |
| `python3 3_apply/inherit_mcp.py` | copy your Claude MCP servers into worker profiles (`--list`, `--dry-run`) |
| `python3 3_apply/inherit_all.py` | register those MCP servers with every engine's own CLI (codex/opencode/agy/copilot) |

Environment knobs (all optional): `CAO_SUPERVISOR_PROVIDER` forces the supervisor
engine · `CAO_FALLBACK_PROVIDER` sets the auto-retry engine · `LOCAL_API_KEY`
(in `.env`) authenticates the coding-worker endpoint.

## 1. Install (once)

```sh
git clone <this-repo-url> ~/cao-setup
cd ~/cao-setup
cp .env.example .env               # set LOCAL_API_KEY (bulk-worker endpoint key)
./1_install/bootstrap.sh
```

Flags: `--inherit-mcp` (give your existing Claude MCP servers to the workers),
`--with-kodeks` (dev standard — read its section first), `--with-guard-hook`.

Prerequisites: macOS needs [Homebrew](https://brew.sh); Linux needs `sudo` (for
`apt`). Scripts clone executable — no `chmod` needed.

Then the interactive logins the installer prints (only a human can do these):

```sh
claude          # /login on first use
codex login     # ChatGPT sign-in
agy             # Google sign-in if prompted
```

## 2. Configure — one file

Edit `2_configure/cao.config.toml`, then `./3_apply/apply.sh`. That's the loop.

| Section | Controls |
|---------|----------|
| `[orchestrator]` | supervisor, default provider, port, max workers, worktree isolation |
| `[endpoint]` | bulk-worker `base_url`, `models`, `default_model` |
| `[workers.*]` | each worker's `provider` and `model` |
| `[profiles]` | which profiles register, in what order |

`apply.sh` renders the toml into `~/.config/cao/settings.json`,
`~/.aws/opencode/opencode.json`, and each worker's frontmatter, re-registers
them, and offers to restart the server. Renaming a worker is safe: `apply.sh`
prunes the old profile from every store cao uses, so no ghost is left behind.

**Coding worker model.** The coding role (`coder_worker`) runs the cheap,
high-volume half of the work through `opencode` against any OpenAI-compatible
endpoint — set `[endpoint]` `base_url` to OpenRouter or another gateway and pick
a low-cost model. If you'd rather not run a separate cheap endpoint, set
`workers.coder_worker.provider` to `claude_code`, `codex`, or `antigravity_cli`
and the coding role runs on that engine instead — no external key needed.

## 3. Roles — who does what, from one place

Every role lives in `[workers.*]` in `cao.config.toml`:

```toml
[workers.codex_worker]
provider = "codex"                       # which engine
model    = "..."                         # optional (opencode only)
aliases  = ["codex", "frontend", "ui"]   # how the supervisor routes to it
focus    = "React/Vue/Svelte, CSS, UI"   # what it does
```

`apply.sh` writes `provider`/`model` into the worker's frontmatter **and
regenerates the supervisor's routing table** from `aliases` + `focus` — so this
one block controls engine, model, and responsibility. Change `focus`/`aliases`
to reassign work; change `provider` to move a role onto another engine.

Only the **detailed prompt** (execution rules) lives separately, in
`2_configure/prompts/<worker>.md` below the frontmatter — edit it there for
fine behavior. `apply.sh` never touches that text; it only regenerates the
supervisor's routing table (between the `AUTO-MAPPING` markers).

After any edit: `./3_apply/apply.sh`.

## 4. Run

```sh
cao-run
```

First it runs a **pre-flight health check** (`cao-doctor`) — verifies the
toolchain, worker binaries, logins, and that the bulk endpoint answers, so a
worker can't fail silently mid-task. A missing binary aborts the launch;
warnings (e.g. an unconfigured endpoint) don't. Run it any time with
`cao-doctor`, or skip the gate with `cao-run --skip-check`.

Then it launches the daemon if needed and attaches you to the supervisor (tmux
session `cao-supervisor`). Delegate by talking to it. You can detach (`Ctrl-b
d`) and the workers keep running — the `cao-server` daemon owns them, not your
terminal. Reattach with `tmux attach -t cao-supervisor`.

> **Run it in a real terminal, not an IDE-embedded one.** Some IDE integrations
> (e.g. Zed) strip the supervisor's file-edit tools; it then can't delegate and
> falls back to hand-holding you through manual edits. A plain terminal keeps
> full tools. (Workers run in the daemon and are unaffected either way.)

### Supervisor fallback (when Claude's quota runs out)

The supervisor defaults to `claude_code`. If your Claude quota is exhausted or
your login expires, `cao-run` no longer dead-ends — it picks the supervisor
engine in this priority:

1. **`CAO_SUPERVISOR_PROVIDER`** env var — explicit override, always wins:
   ```sh
   CAO_SUPERVISOR_PROVIDER=antigravity_cli cao-run
   ```
2. **Fallback hint** — `cao-doctor` writes `~/.cao/supervisor_provider` when it
   sees Claude logged out, and clears it when Claude works again.
3. **`claude_code`** default.

On top of that, when the primary is `claude_code`, `cao-run` **auto-retries once
on a fallback engine if the launch itself fails** — this catches a burned quota,
which isn't visible any earlier (`claude auth status` reports login, not quota).
Fallback order: `CAO_FALLBACK_PROVIDER` env > `antigravity_cli` (if `agy`
present) > `codex`. Any registered worker engine works as the value.

**Stop when done.** Nothing auto-stops — workers survive detach by design, so
you shut down explicitly:

```sh
cao-stop              # kill all cao- tmux sessions + the daemon (end of day)
cao-stop --workers    # kill workers only, keep the supervisor + daemon up
cao-stop --keep-server / -k   # kill the sessions, leave the daemon running
```

**Check usage.** `cao-tokens` scrapes each CLI's local store (`~/.claude` jsonl,
`~/.codex` + opencode sqlite) — no billing API. By **default it shows a claude
heatmap plus a per-day table across all engines, last 7 days, cao-only** — one
column per engine, each cell `input/output` (compact: `2.2k/670.5k`):

```
date          claude(in/out)   ~codex  ~opencode(in/out)      $
2026-09-17       2.2k/670.5k     2.1M         2.8M/26.6k   0.00
```

- **cao-only is the default.** For claude it counts only sessions that loaded
  cao's MCP server (a reliable marker). codex and opencode keep no such marker
  locally, so their columns are marked `~` and show *all* of that engine's use —
  in practice you rarely run them outside cao. A precise per-engine split would
  need request tracing (e.g. langfuse). `--all-sessions` drops the claude filter.
- `output` is real generation — the number that matters. `codex` reports one
  combined total (no in/out split). `$` shows only for opencode (metered); claude
  and codex are flat-rate. `agy`/gemini keeps no local log (Google server-side).

```sh
cao-tokens                # DEFAULT: heatmap + per-day, all engines, 7 days, cao-only
cao-tokens --since 2w     # widen the window (24h / 7d / 2w / 3d ...)
cao-tokens --lifetime     # lifetime per-engine table (all history)
cao-tokens --day 2026-09-17   # one specific date (YYYY-MM-DD)
cao-tokens --claude       # per-day CLAUDE only (input/output/cache detail)
cao-tokens --heatmap      # claude output heatmap only
cao-tokens -x             # extended: heatmap + claude daily + lifetime table
cao-tokens --all-sessions # include non-cao claude sessions too
cao-tokens --json         # machine-readable form of the selected view
```

**Design first for big work.** For a new project or a large feature the
supervisor acts as architect: it discusses the system with you, writes a Mermaid
sequence/flow diagram to `wcao/design/`, and gets your approval before
any code is delegated — the diagram is the contract the workers build against.
Small changes skip this and go straight to delegation. The diagram is a living
document: it's referenced and edited across sessions, not redrawn each time.

**Single Source of Truth (`wcao/`).** All project-level plans, contracts, and knowledge live in `wcao/`:
- `wcao/plans/now.md` — Active plan, North Star objective, and latest checkpoint.
- `wcao/tasks.json` — Directed Acyclic Graph (DAG) of tasks with dependencies and file locks.
- `wcao/design/*.mmd` — Architecture and sequence diagrams.
- `wcao/skills/*.md` — Procedural memory (rules, workflows, tool gotchas).
- `wcao/audit/` — Postflight audit reports and test scorecards.
- `wcao/memory.sqlite` — Local episodic memory database with BM25 FTS5 full-text search (gitignored).

## Autonomous Execution & Self-Healing (`cao_auto`)

`cao_auto` provides fully headless, autonomous execution of task graphs:

```sh
python run/cao_auto.py --tasks wcao/tasks.json --max-workers 4
```

1. **Autonomous Planning (`cao-plan`)**: Decomposes a high-level goal into an acyclic DAG (`wcao/tasks.json`) with TokenMaster model routing and contract specification.
2. **DAG Scheduling & File Locks**: Evaluates `depends_on` relationships and prevents concurrent workers from touching overlapping `files`, ensuring zero merge conflicts or race conditions.
3. **Proactive TokenMaster Quota Control**: Reads live quota utilization via `cao_limits`. If quota exceeds the 80% watermark or is blocked, it proactively reassigns tasks to `hermes_worker` or `coder_worker` before hitting rate limits.
4. **Anti-Test-Tampering Gate**: During postflight audit, inspects git diffs to ensure workers have not weakened assertions, inserted bypasses (`assert True`), or deleted test functions. Automatically reverts tampered tests and forces fixes in production code.
5. **Architect Escalation Protocol**: If a bulk implementation worker fails to fix an audit blocker on attempt 1, self-healing automatically escalates attempt 2+ to an Architect/Reasoning engine (`hermes_worker` or `claude_worker`) for root-cause diagnosis.

## Hermes Learning & Memory System

CAO incorporates the **Hermes Continuous Learning** architecture across all engines:

1. **Episodic Memory (`cao-memory`)**:
   Powered by SQLite with FTS5 and BM25 ranking. Stores context, past solutions, and debugging outcomes.
   - `cao-memory store <category> <summary> [details]`
   - `cao-memory recall <query> [-n 5]`
   - `cao-memory list [--category <cat>]`
   Before any task is dispatched, `cao_auto` automatically searches episodic memory and injects relevant historical lessons directly into the worker's prompt.
2. **Procedural Memory (`wcao/skills/`)**:
   Reusable behavioral and debugging recipes saved as Markdown files in `wcao/skills/`, shared across all worker engines.
3. **Hermes 50% Compaction Rule**:
   To prevent context saturation, the `ContextCompactor` automatically triggers every 5 turns or when context fills. It condenses verbose conversation histories into structured summaries, extracts new lessons, and writes progress checkpoints directly to `wcao/plans/now.md`.
4. **Retrospective Storage**:
   Whenever a self-healing loop resolves a failure, the root cause and fix are automatically indexed into `memory.sqlite` and `wcao/skills/` so future workers never repeat the mistake.

## Share your MCP servers with every engine

MCP is a cross-engine protocol — codex, opencode, antigravity (agy), and copilot
each have their own `mcp add`, so an MCP tool you use in Claude (lean-ctx,
symdex, …) can reach all of them. Two scripts, two levels:

```sh
# 1. Into cao WORKER PROFILES (cao writes them into each engine's config at install):
python3 3_apply/inherit_mcp.py --list      # what you have
python3 3_apply/inherit_mcp.py             # add to all worker profiles
./3_apply/apply.sh                         # push live

# 2. Directly into every ENGINE's own CLI config (works outside cao too):
python3 3_apply/inherit_all.py --list      # per-engine plan
python3 3_apply/inherit_all.py --dry-run   # print the mcp-add commands
python3 3_apply/inherit_all.py             # register with codex/opencode/agy/copilot
```

Both read `~/.claude.json` global `mcpServers` (skipping cao's own server). A
server carrying a token in its `env` is copied verbatim — the scripts warn so you
can review. `bootstrap.sh --inherit-mcp` runs both automatically.

### Plugins & skills — `cao-plugins`

Plugins (caveman, karpathy, superpowers, …) are git repos / folders that ship a
manifest per engine, so each engine takes them its own way. `cao-plugins` reads
what Claude has and pushes MCP + plugins out to every engine:

```sh
cao-plugins list                     # what each engine currently has
cao-plugins broadcast --dry-run      # show the plan, run nothing
cao-plugins broadcast                # push all Claude MCP + plugins everywhere
cao-plugins broadcast --mcp          # MCP only
cao-plugins broadcast --plugins      # plugins/skills only
cao-plugins broadcast --only=caveman # just one plugin
cao-plugins broadcast --to=codex,agy # just these engines
```

How each engine receives a plugin:

| Engine | Plugin path |
|--------|-------------|
| claude | native (already installed) |
| codex  | `plugin marketplace add owner/repo` + `plugin add p@mp` (git) |
| agy    | `plugin install <plugin-dir>` (local folder) |
| copilot | `skill add <plugin-dir>`; also reads `.claude/skills` natively |
| opencode | no git/dir plugin path — gets a **compact skill index** (name + one line each) appended to `~/.config/opencode/AGENTS.md`, which it reads as instructions |

So MCP and real plugins reach claude/codex/agy/copilot; opencode gets the skills
as a lightweight text index (one line per skill, not full bodies — to avoid
bloating every opencode run). Nothing is ever uninstalled.

### Don't have any yet? Context MCP servers worth adding

`inherit_mcp.py` only copies servers you **already** have. If your `--list` is
empty, these two give the workers a big context/token win before you inherit —
they let a worker read, search, and map the repo compactly instead of pulling
whole files into its context:

- **lean-ctx** — cached, compressed file reads + git/grep output. Cuts the tokens
  a worker spends just to look at code.
- **symdex** — symbol index: "who calls X", file/repo outlines, dependency maps.
  This is exactly what `analyst_worker` leans on.

Add them to your **own** Claude first (they live in `~/.claude.json` global
`mcpServers`), confirm with `python3 3_apply/inherit_mcp.py --list`, then run the
inherit + apply steps above to push them to every worker. They're independent,
optional tools — CAO works without them; they only make each worker cheaper.

Skills like **superpowers** (brainstorming, systematic-debugging) are Claude
Code-only and can't reach codex/opencode/antigravity workers. Install them in
your own Claude if you want them on the **supervisor** (which runs on Claude);
the non-Claude workers won't see them either way.

## Secrets

`LOCAL_API_KEY` is the only secret — in `.env` (gitignored), copied to
`~/.config/cao/cao.env` (chmod 600), never in a tracked file (configs reference
it as `{env:LOCAL_API_KEY}`). Endpoint URL and model ids are not secret.

## After `cao update`

Re-run `./1_install/bootstrap.sh` — it re-applies the pyte patch (which lives in
the CAO venv and is lost on reinstall). Idempotent.

## dev-kodeks (optional development standard)

`--with-kodeks` installs [dev-kodeks](https://github.com/povchingiz/dev-kodeks):
global Claude Code rules + skills for repo/code/change discipline. A **quality
layer**, not part of CAO — it runs fine without it.

⚠️ **It's global**: it symlinks into `~/.claude/`, so it affects *every* Claude
session on the machine, including the CAO workers that run through `claude`, and
changes Claude's default behavior (planning discipline, when it pauses). Enable
deliberately. `--with-guard-hook` also activates its `guard-env` hook, which
blocks `git push/pull/reset`, `systemctl`, `shutdown` … — for the workers too.
Both are off unless you pass the flag.

---

### For Claude: "set it all up for me"

If a user hands you this repo and says *connect everything*, do this in order —
stop at each 🔸 (needs a human):

1. Confirm OS is macOS/Linux (Windows → tell them WSL2 per `WINDOWS.md`, stop).
2. 🔸 Ask for `LOCAL_API_KEY`; `cp .env.example .env` and write it. Never print
   or commit it.
3. Check `[endpoint]` in `2_configure/cao.config.toml` matches their endpoint.
4. Run `./1_install/bootstrap.sh` (add `--inherit-mcp` / `--with-kodeks` only if
   they ask).
5. 🔸 Tell them to run the logins themselves: `claude` → `/login`, `codex
   login`, `agy`. You cannot.
6. Verify: `cao-run`, delegate a trivial task to each worker, confirm replies.
7. Point them at `cao-run` from any project. Edits go through `2_configure/` +
   `./3_apply/apply.sh`, never the live files.
