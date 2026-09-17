# cao-setup

Set up a **CLI Agent Orchestrator (CAO)** on macOS or Linux: one Claude
supervisor that delegates to four worker engines. This repo installs it,
configures it, and keeps every setting in one place.

```
cao-run  →  supervisor (Claude)  →  assign  →  ┌ claude_worker      architecture, contracts
                                               ├ opencode_worker    bulk: schemas, CRUD (cheap model)
                                               ├ codex_worker        frontend / UI
                                               └ antigravity_worker  QA, tests, review
```

Roles above are the **defaults** — every one is editable (see *Configure*).

> **Windows:** not supported natively (CAO needs tmux + POSIX ptys). Use WSL2 —
> see [WINDOWS.md](WINDOWS.md). Inside WSL these steps apply unchanged, if the
> repo lives in your WSL home (not `/mnt/c`).

## Repo layout — by lifecycle phase

```
1_install/     bootstrap.sh · bootstrap.ps1 · patch_pyte.py     ← run once
2_configure/   cao.config.toml · prompts/*.md                   ← edit these
3_apply/       apply.sh · render_config.py · inherit_mcp.py     ← push edits live
run/           cao-run                                          ← launch
.generated/    settings.json · opencode.json    ← auto-written locally (gitignored)
```

Edit only in `2_configure/`. Everything else is machinery. Never edit the live
files under `~/.aws` or `~/.config` directly — they are generated.

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
them, and offers to restart the server.

**Bulk worker model.** The bulk role runs the cheap, high-volume half of the
work through `opencode` against any OpenAI-compatible endpoint — set `[endpoint]`
`base_url` to OpenRouter or another gateway and pick a low-cost model. If you'd
rather not run a separate cheap endpoint, set `workers.opencode_worker.provider`
to `claude_code`, `codex`, or `antigravity_cli` and the bulk role runs on that
engine instead — no external key needed.

## 3. Roles — who does what

Two independent knobs, both editable:

- **What a worker does** → its prompt in `2_configure/prompts/<worker>.md`
  (the text below the frontmatter). `apply.sh` never rewrites prompt text.
- **Who the supervisor routes to** → the worker mapping in
  `2_configure/prompts/code_supervisor.md`. Change the aliases/targets to
  re-assign responsibilities.
- **Which engine/model a role runs on** → `[workers.*]` in `cao.config.toml`.

After any edit: `./3_apply/apply.sh`.

## 4. Run

```sh
cao-run
```

Launches the daemon if needed and attaches you to the supervisor (tmux session
`cao-supervisor`). Delegate by talking to it. You can detach (`Ctrl-b d`) and
the workers keep running — the `cao-server` daemon owns them, not your terminal.
Reattach with `tmux attach -t cao-supervisor`.

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
