# cao-setup

One script sets up a CLI Agent Orchestrator (CAO) on a fresh **macOS** or
**Ubuntu/Linux** machine: installs CAO and four worker CLIs, wires their
configs, and applies the fixes needed to run them.

`cao-run` then launches a Claude **supervisor** that delegates to four workers:

| Worker | Engine | Role |
|--------|--------|------|
| claude_worker | Claude Code | architecture, contracts, hard logic |
| opencode_worker | opencode + DeepSeek-V4-Pro | bulk: scaffolding, schemas, CRUD |
| codex_worker | Codex (ChatGPT plan) | frontend / UI |
| antigravity_worker | Antigravity (Gemini) | QA, tests, review |

> **Windows:** not supported natively (CAO needs tmux + POSIX ptys). Use
> **WSL2** — see [WINDOWS.md](WINDOWS.md). Inside WSL these steps apply
> unchanged, if the repo lives in your WSL home (not `/mnt/c`).

<!-- ===================================================================== -->
<!-- FOR CLAUDE (or any coding agent) asked to "set this up" / "connect    -->
<!-- everything". Follow this exactly; don't improvise the order.          -->
<!-- ===================================================================== -->

## For Claude: "set it all up for me"

If the user handed you this repo and said *"connect everything"*, do this — and
**stop to ask the user** at each 🔸 (those need a human):

1. **Read first.** Skim this README and `cao.config.toml`. Confirm the OS is
   macOS or Linux (on Windows, tell the user to use WSL2 per `WINDOWS.md` and
   stop).
2. **Secret.** 🔸 Ask the user for their `LOCAL_API_KEY` (the bulk-worker
   endpoint key). `cp .env.example .env` and write it in. Never print it, never
   commit `.env`.
3. **Endpoint/models.** Confirm `[endpoint]` in `cao.config.toml` matches the
   user's endpoint (`base_url`, `models`, `default_model`). Adjust if they use a
   different one.
4. **Run the installer:** `./bootstrap.sh`. Add `--inherit-mcp` if the user
   wants their existing Claude MCP servers given to the workers. Add
   `--with-kodeks` only if they explicitly want the dev standard (it's global —
   see the dev-kodeks section before offering it).
5. **Logins.** 🔸 These are interactive and only the user can do them — tell them
   to run, in their terminal: `claude` (then `/login`), `codex login`, and `agy`
   (Google sign-in). You cannot do these for them.
6. **Verify.** Once logged in, run a smoke test: `cao-run`, then ask the
   supervisor to delegate a trivial task to each worker and confirm a reply.
7. **Done.** Tell the user to launch with `cao-run` from any project directory.

Everything is editable from this repo — change `cao.config.toml` or a prompt in
`agent_store/`, then `./apply.sh`. Do not edit the live files under `~/.aws` or
`~/.config` directly; they are generated.

## Prerequisites

- **macOS:** [Homebrew](https://brew.sh) installed.
- **Ubuntu/Linux:** `sudo` access (bootstrap uses `apt` for missing packages).
- Everything else (uv, node, worker CLIs) is installed by `bootstrap.sh`.

## Quick start

```sh
git clone <your-fork-or-this-repo-url> ~/cao-setup
cd ~/cao-setup
cp .env.example .env          # set LOCAL_API_KEY (endpoint key for the bulk worker)
./bootstrap.sh
```

The scripts are committed executable, so `git clone` on macOS/Linux/WSL keeps
the `+x` bit — no `chmod` needed. If you ever get "permission denied", run
`chmod +x bootstrap.sh apply.sh cao-run`.

Optional flags:

```sh
./bootstrap.sh --with-kodeks              # + dev-kodeks Claude rules layer
./bootstrap.sh --with-kodeks --with-guard-hook  # + guard-env safety hook
```

Then the interactive logins the script prints, and launch:

```sh
claude          # /login on first use
codex login     # ChatGPT browser sign-in
agy             # Google sign-in if prompted
cao-run
```

## What bootstrap does

1. Installs missing prereqs (`python3`, `tmux`, `node`/`npm`, `uv`) — brew on mac, apt on Linux.
2. Installs CAO: `uv tool install` from `awslabs/cli-agent-orchestrator@main`.
3. Installs workers via npm (`@anthropic-ai/claude-code`, `@openai/codex`, `opencode-ai`) + `agy` via its official installer.
4. Renders `cao.config.toml` into the live config and registers all profiles.
5. Patches pyte (Antigravity ANSI crash), skips Antigravity onboarding, empties `~/.codex/hooks.json` (its hook otherwise blocks init).
6. Optional dev-kodeks + guard-env hook.

## Inherit your existing MCP servers

Whatever MCP servers you already use in Claude (in `~/.claude.json`) can be
handed to the CAO workers — so an orchestrated agent gets the same tools your
own Claude session has. Because CAO writes each profile's `mcpServers` into the
target engine's native config, this reaches **every** worker, not just the
Claude one.

```sh
python3 inherit_mcp.py --list      # show what you have to inherit
python3 inherit_mcp.py --dry-run   # show the plan, write nothing
python3 inherit_mcp.py             # add them to all worker profiles
./apply.sh                         # push into the live engine configs
```

Or during setup: `./bootstrap.sh --inherit-mcp`.

- **Source:** `~/.claude.json` global `mcpServers` only (the standard place).
  `cao-mcp-server` is skipped (workers already have it). Plugin-provided and
  per-project MCP are **not** auto-read — enabled-state makes them unreliable to
  copy blindly; add those by hand.
- **Which engines:** MCP is a protocol, so any MCP-capable worker loads them —
  claude, codex, opencode, antigravity all do. **Skills** (e.g. superpowers)
  are Claude-only markdown, not MCP, and cannot be inherited this way — copy
  their guidance into a worker's prompt if you want it.
- **Secrets:** server definitions are copied verbatim into the profile files.
  If a server carries a token in its `env`, that token lands in the profile —
  the script warns; review before committing. Prefer servers that read their
  own env var.

## Change settings — one file

Edit **`cao.config.toml`**, run **`./apply.sh`**. That's the whole workflow.

| Section | Controls |
|---------|----------|
| `[orchestrator]` | supervisor, default provider, port, max workers, worktree isolation |
| `[endpoint]` | bulk-worker `base_url`, `models` list, `default_model` |
| `[workers.*]` | each worker's `provider` and (opencode) `model` |
| `[profiles]` | which profiles register, and in what order |

`apply.sh` writes the real files CAO reads — `~/.config/cao/settings.json`,
`~/.aws/opencode/opencode.json`, and each worker's `.md` **frontmatter** — then
re-registers and offers to restart the server. All under your home dir; no sudo.

**Worker prompts** live in `agent_store/<worker>.md` (the text below the
frontmatter). Edit those directly, then `./apply.sh` to push them. `apply.sh`
never rewrites prompt text — only the `provider:`/`model:` metadata lines.

## Daily loop

- Setting (model, port, endpoint): edit `cao.config.toml` → `./apply.sh`
- Prompt: edit `agent_store/<worker>.md` → `./apply.sh`
- New machine: `./bootstrap.sh`
- After `cao update`: re-run `./bootstrap.sh` (re-applies the pyte patch; idempotent)

## Secrets

`LOCAL_API_KEY` is the only secret. It lives in `.env` (gitignored), is copied
to `~/.config/cao/cao.env` (chmod 600), and is **never** written into any
tracked file — configs reference it as `{env:LOCAL_API_KEY}`. The endpoint URL
and model ids in `cao.config.toml` are not secret.

## Files

| Path | What |
|------|------|
| `cao.config.toml` | **single source of truth** for non-secret settings |
| `apply.sh` | render config + prompts into live CAO, re-register, restart |
| `render_config.py` | toml → settings.json / opencode.json / worker frontmatter |
| `inherit_mcp.py` | copy your `~/.claude.json` MCP servers into worker profiles |
| `bootstrap.sh` | first-time provisioner (idempotent) |
| `bootstrap.ps1` | Windows helper: sets up WSL2, hands off to `bootstrap.sh` |
| `cao-run` | launcher: starts daemon, injects key, launches supervisor |
| `agent_store/*.md` | 5 CAO profiles; **prompt bodies live here** |
| `config/*.json` | generated snapshots — regenerated by `apply.sh` |
| `patches/patch_pyte.py` | idempotent pyte fix |
| `.env.example` | template for `LOCAL_API_KEY` |

## dev-kodeks (optional development standard)

`--with-kodeks` installs [dev-kodeks](https://github.com/povchingiz/dev-kodeks):
a personal development standard for Claude Code — repo structure, a
prototype→production path, and a change register. It is a **quality layer**, not
part of CAO; the orchestrator runs fine without it. **Off by default** — you opt
in.

**What you get** (three skills that trigger by topic, plus a global `CLAUDE.md`):

| Skill | Helps with |
|-------|-----------|
| `repo-standard` | directory layout, root cleanliness, `.env` hygiene, lockfiles, `Makefile`/CI, where a file belongs (12-factor-ish) |
| `code-standard` | hardening from prototype to prod — timeouts/retries/idempotency, error handling, API contracts, logging/metrics |
| `change-standard` | a `PLAN.md`/`TEST-PLAN.md` register: acceptance criteria, test scenarios, architecture checks |

This is genuinely useful if you want your projects to come out structured and
standardized instead of ad-hoc.

### ⚠️ Read before enabling — it changes how Claude behaves, everywhere

`dev-kodeks`'s `install.sh` **symlinks into `~/.claude/`**, so it is **global,
not per-project**:

- **Every Claude Code session on the machine** picks it up — all your repos,
  and this terminal. You do not choose where it applies.
- **CAO workers inherit it too.** `claude_worker` and `code_supervisor` run
  through the `claude` binary, so its global `CLAUDE.md` (a "scale gate" and
  work-phase rules: *execution asks zero questions, stops only on
  irreversible/external actions*) layers on top of each worker's own prompt.
  Usually complementary, occasionally competing — know it's there if a worker
  behaves more cautiously than its profile alone implies.
- It **changes Claude's default behavior** (planning discipline, when it pauses).
  That's the point — but enable it deliberately, not by accident.

Enable only if you want that standard applied machine-wide. To try it in one
project first instead, clone dev-kodeks and read its own README rather than
installing globally here.

### The guard-env hook (extra opt-in)

`--with-guard-hook` (implies `--with-kodeks`) also activates dev-kodeks's
`guard-env` PreToolUse hook, which **blocks** irreversible/environment commands
(`git push/pull/reset`, `systemctl`, `shutdown`, …) and prints them for you to
run by hand. Because CAO workers run through `claude`, this blocks those
commands **for the workers too** — safer, but it will stop a worker mid-task if
it tries to `git push`. Off unless you pass the flag; a `settings.json` backup
is written when it's activated.
