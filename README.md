# cao-setup

Set up a **CLI Agent Orchestrator (CAO)** on macOS or Linux: one Claude
supervisor that plans work and delegates it to a team of specialist worker
engines — each on the CLI that's best (and cheapest) at its job. This repo
installs it, configures it from one file, and keeps every setting in one place.

```
cao-run  →  supervisor (Claude, Tech Lead)  →  assign  →
    ┌ claude_worker       claude       architecture, contracts, hard logic
    ├ coder_worker        opencode     implementation, schemas, CRUD (cheap model)
    ├ analyst_worker      gemini/agy   whole-repo maps, long docs, multimodal (huge context)
    ├ codex_worker        codex        frontend / UI
    └ antigravity_worker  gemini/agy   QA, tests, security review
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
1_install/     bootstrap.sh · bootstrap.ps1 · patch_pyte.py     ← run once
2_configure/   cao.config.toml · prompts/*.md                   ← edit these
3_apply/       apply.sh · render_config.py · inherit_mcp.py     ← push edits live
run/           cao-run · cao-doctor · cao-stop · cao-tokens     ← launch · check · stop · usage
.generated/    settings.json · opencode.json    ← auto-written locally (gitignored)
```

Edit only in `2_configure/`. Everything else is machinery. Never edit the live
files under `~/.aws` or `~/.config` directly — they are generated.

## Command cheatsheet

Every command takes `-h`/`--help`. Nothing here needs arguments to start.

| Command | What it does |
|---------|--------------|
| `cao-run` | health-check, then launch the supervisor (add `--skip-check` to skip the gate) |
| `cao-doctor` | run the pre-flight health check on its own (toolchain, engines, logins, endpoint) |
| `cao-tokens` | per-day usage across **all engines**, last 7 days (cells are in/out); `--since 2w`, `--all`, `--day DATE`, `--claude`, `--heatmap`, `--cao-only` |
| `cao-stop` | end the session: stop daemon + tmux sessions (`--workers` keeps supervisor, `-k` keeps daemon) |
| `./3_apply/apply.sh` | push `2_configure/` edits live (renders config, re-registers, offers restart) |
| `python3 3_apply/inherit_mcp.py` | copy your own Claude MCP servers into the workers (`--list`, `--dry-run`) |

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
`~/.codex` + opencode sqlite) — no billing API. By **default it shows a per-day
table across ALL engines, for the last 7 days** — one column per engine, each
cell `input/output` (compact: `2.2k/671.8k`):

```
date          claude(in/out)    codex   opencode(in/out)      $
2026-09-17       2.2k/671.8k     2.1M         2.8M/26.6k   0.00
```

- `output` is real generation — the number that matters. `codex` reports one
  combined total (no in/out split). `$` shows only for opencode (its endpoint is
  metered); claude and codex are flat-rate subscriptions. `agy`/gemini keeps no
  local usage log, so it can't appear (Google quota is server-side).

```sh
cao-tokens                # DEFAULT: per-day, all engines, last 7 days
cao-tokens --since 2w     # widen the window (24h / 7d / 2w / 3d ...)
cao-tokens --all          # lifetime per-engine table (all history)
cao-tokens --day 2026-09-17   # one specific date
cao-tokens --claude       # per-day CLAUDE only (input/output/cache detail)
cao-tokens --heatmap      # GitHub-style calendar of claude output
cao-tokens -x             # extended: heatmap + claude daily + lifetime table
cao-tokens --cao-only     # only cao-driven claude sessions
cao-tokens --json         # machine-readable form of the selected view
```

> The claude figure counts EVERY Claude Code session on this machine, not just
> cao's — a big number is your ordinary Claude use, not "cao burning limits".
> `--cao-only` isolates cao-driven sessions (claude-only, since only claude
> sessions carry the cao marker).

**Design first for big work.** For a new project or a large feature the
supervisor acts as architect: it discusses the system with you, writes a Mermaid
sequence/flow diagram to `cao_session/design/`, and gets your approval before
any code is delegated — the diagram is the contract the workers build against.
Small changes skip this and go straight to delegation. The diagram is a living
document: it's referenced and edited across sessions, not redrawn each time.

**How work is tracked.** The supervisor keeps a per-session board under
`cao_session/session_NNN/` — `plan.md` (agreed plan), `tasks.json` (the task
graph: each task has an `engine`, the `files` it owns, and `depends_on` edges),
`reports/` (audits), and `context.md` (running log). Independent tasks (no
shared `depends_on`) are dispatched together and run in parallel up to the
worker cap; dependent ones wait. `cao_session/` is gitignored — local working
state, not committed.

**Audit gate before "done".** When the tasks finish, the supervisor runs an
audit through `antigravity_worker`, which reviews style / security / tests /
performance and reports findings with severity levels (`[minor]`…`[critical]`).
A `[critical]` security finding or a failing test is a **blocker**: the
supervisor turns it into a fix-task for the worker that owns that code (the
cheap bulk worker fixes its own output — a strong model isn't spent on it),
re-audits, and repeats until clean. Only then is the session reported complete —
and you still run your own acceptance pass. If dev-kodeks is installed, the
auditor uses its code/security criteria as the rubric.

## Inherit your existing MCP servers

Whatever MCP servers you already use in Claude (`~/.claude.json`) can be handed
to the workers — CAO writes each into the target engine's native config, so it
reaches every worker, not just the Claude one.

```sh
python3 3_apply/inherit_mcp.py --list      # what you have
python3 3_apply/inherit_mcp.py --dry-run   # plan only
python3 3_apply/inherit_mcp.py             # add to all workers
./3_apply/apply.sh                         # push live
```

Skills (e.g. superpowers) are Claude-only markdown, not MCP, and can't be
inherited this way. Source is `~/.claude.json` global `mcpServers` only. A
server carrying a token in its `env` lands in the profile file — the script
warns; review before committing.

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
