# CAO — session plan & state (19 Sep 2026)

Everything from this session in one file: what shipped, the v2 architecture we
designed, and the build order. Open this project in cao and hand the supervisor
this file as the working brief.

---

## Part A — what shipped today (committed)

| Commit | What |
|--------|------|
| `ee25397` | supervisor fallback (env/hint/retry), per-day token views, engine role rework |
| `11856db` | production hardening — robustness, UX, docs |
| `46f63ef` | cao-stop help fix; gitignore python bytecode |
| `06fe488` | apply.sh prunes ghost profiles from every cao store on rename |
| `85aa379` | install cao-* as symlinks (no more stale copies); doctor flags stale |
| `530005c` | cao-tokens per-day table across all engines |
| `3955fec` | cao-tokens cao-only + heatmap by default, --lifetime, --day validation |
| `d2f97e8` | distinguish a busy supervisor session from a quota failure |
| `43a0959` | supervisor terse, stepwise communication style |
| `50e55f1` | supervisor enforce delegation (inspect self, delegate the writing) |
| `d69048c` | broadcast MCP servers to every engine + register copilot worker |
| `dd508d2` | cao-plugins — broadcast Claude MCP + plugins/skills to every engine |

**Uncommitted (ready):** nitec-prefix fix — the `<endpoint>/…` model prefix now
applies ONLY to opencode_cli (other engines name models directly), and the
tracked coder_worker prompt uses a `<endpoint>/<cheap-model>` placeholder so no
real endpoint leaks into git. Files: `3_apply/render_config.py`,
`2_configure/prompts/coder_worker.md`.

### Current tools (all symlinked into ~/.local/bin)
- `cao-run` — pre-flight + launch supervisor; auto-fallback engine on quota/login; detects busy session
- `cao-doctor` — health check (toolchain, engines, logins, endpoint, stale tools, busy session)
- `cao-tokens` — per-day usage across all engines, cao-only + heatmap by default
- `cao-plugins` — broadcast Claude MCP + plugins/skills to every engine
- `cao-stop` — end session
- `3_apply/inherit_mcp.py` (MCP into worker profiles) · `inherit_all.py` (MCP into each engine CLI)

### Current workers (7 profiles)
supervisor(claude) · claude_worker(claude) · coder_worker(opencode/deepseek) ·
codex_worker(codex) · analyst_worker(agy/gemini) · antigravity_worker(agy/qa) ·
copilot_worker(copilot, role TBD)

---

## Part B — CAO v2 architecture (designed, NOT built)

### Core idea
The supervisor plans work into a **task list up front**, assigning each task an
**engine + model chosen for its strength**. A **token-limit master** watches how
close each engine is to its quota and **reassigns models/engines** as limits run
out — both while planning (respect budgets) and during execution (swap on the
fly). A **monitor** shows the whole task list: status, executor, timestamps,
comments, QA verdict.

### Role template (defaults — planner may override per task)
Roles are functions; the executor is chosen by model strength. Every engine is a
multi-vendor gateway (vendor/api_url/key/model configurable).

| Role | Default engine · model | Why |
|------|------------------------|-----|
| Architect | claude · opus | hardest reasoning, contracts |
| Frontend | codex · gpt | UI/React |
| Bulk coder | opencode · deepseek | cheap high-volume code |
| Analyst | agy · gemini-flash (big ctx) | reads the WHOLE repo cheaply |
| QA | agy · gemini / claude-via-agy | tests, security |
| GitHub ops | copilot · gpt | PRs, issues, releases |
| future | vercel / railway / supabase | each has its own plugins+MCP |

Gateway note: **agy exposes Gemini Flash/Pro AND Claude Opus/Sonnet 4.6 AND
GPT-OSS**; copilot exposes GPT + BYOK. So Claude can run through agy on a
DIFFERENT quota than the main subscription — the basis for fallback.

### What the Analyst does
The team's eyes. On a big/unfamiliar repo, reading files one by one burns tokens.
Instead: Analyst (Gemini, huge context) reads the whole repo once → a reference
map (modules, data flow, "where is X / who calls it / what breaks if changed") +
the sequence diagram → **indexes it into lean-ctx** so every worker reads the
project's shape cheaply. Skip for small, understood changes. (Spike: exact
lean-ctx write path.)

### Token-limit master — measured facts
| Engine | Limit signal | Quality |
|--------|--------------|---------|
| **claude** | `-p --output-format=stream-json` → `rate_limit_info`: status (allowed/allowed_warning/rejected), utilization (0–1), rateLimitType, resetsAt, unifiedWindows (five_hour+seven_day) | **proactive** |
| codex | `exec --json` → per-turn usage tokens; no quota remaining | reactive |
| agy/gemini | server-side quota, nothing local | reactive (429) |
| copilot | nothing local | reactive |

Proactive for claude (the scarcest resource — lucky); reactive for the rest.
As of this session Claude's seven_day window was at **utilization 0.89**.

Behavior:
- **Planning:** claude utilization + resetsAt say how much Claude budget is left
  this window; if near full, route reasoning to agy-Claude or Gemini Pro.
- **Execution:** after each claude turn read rate_limit_info; on `rejected` (or
  past a utilization threshold) swap that role to a fallback and note it. On any
  worker's limit error, reassign the task to a capable non-limited peer.
- **Fallback ladder (example):** claude-opus → agy(claude-opus-4-6) →
  agy(gemini-3.1-pro) → codex. Configurable.
- **Reality:** remaining quota for codex/agy/copilot is unknowable without a 429;
  cao-tokens shows spend, not ceiling. Budget-planning is exact for Claude,
  approximate elsewhere.

### Planner — enriched tasks.json
Add to today's {id,title,detail,engine,files,depends_on,status}: `role`, `model`,
`created_at`, `started_at`, `done_at`, `comments[]` ({by,at,text}),
`qa` ({verdict: pass|blocker|none, by, notes}). Planner writes the list up front;
token-master may rewrite engine/model as limits change (each swap appends a
comment).

### cao-monitor — the board (like cao-tokens, for tasks)
Reads `cao_session/*/tasks.json` and shows: status + executor (id, title, status,
role, engine·model), timestamps (created/started/done + duration), comments + QA
verdict, and `--watch` for live refresh. Read-only.

### Multi-project (open)
`cao-run` hardcodes session-name `supervisor`; `cao launch` accepts any
`--session-name` + `--working-directory`, so per-project is feasible
(`cao-<project>`, `cao-stop` finds them by the `cao-` prefix). Cost: more tmux
sessions per project. Plain Claude has no tmux overhead, but cao needs daemon+tmux
for orchestration — the price of multi-agent. Decision deferred.

---

## Part C — build order
1. **cao-limits** — read limits from every engine (claude fully, others best-effort). Foundation for token-master.
2. **Role template + agy-Claude fallback** — set defaults; supervisor falls back to agy-Claude when the main Claude window is spent.
3. **Planner** — enrich tasks.json + supervisor prompt to plan up front.
4. **cao-monitor** — board viewer with `--watch`.
5. **token-master loop** — wire cao-limits into planning + execution swaps.
6. **Multi-project** + specialist workers (vercel/railway/supabase) — last.

Open spikes: analyst→lean-ctx index path; codex/agy/copilot reactive-limit
strings; per-model prefix (opencode-only prefix already fixed).
