# CAO v2 — token-aware planning & multi-model orchestration

Design doc (on paper first, before building). Captures the target architecture
we discussed: role templates by model strength, a task planner, a token-limit
master, and a monitor. Nothing here is built yet — this is the contract.

---

## 1. The core idea

The supervisor plans work into a **task list up front**, assigning each task an
**engine + model chosen for its strength**. A **token-limit master** watches how
close each engine is to its quota and **reassigns models/engines** as limits run
out — both while planning (respect budgets) and during execution (swap on the
fly). A **monitor** shows the whole task list: status, executor, timestamps,
comments, QA verdict.

```
        ┌─────────────── supervisor (planner) ───────────────┐
        │  reads inputs → task list (engine+model per task)   │
        │  consults token-limit master for budgets            │
        └───────────────┬─────────────────────────────────────┘
                        │ tasks.json (enriched)
      ┌─────────────────┼───────────────────────────┐
      ▼                 ▼                            ▼
  workers          token-limit master           cao-monitor
 (by role)         watches limits, swaps         reads tasks.json
                   models when they burn          shows status/QA/time
```

## 2. Role template (defaults — planner may override per task)

Roles are **functions**; the executor is chosen by model strength. Every engine
is a multi-vendor gateway (vendor / api_url / key / model configurable), so a
role can move to whatever model is strongest and available.

| Role | Default engine · model | Why this model |
|------|------------------------|----------------|
| **Architect** | claude · opus | hardest reasoning, contracts |
| **Frontend** | codex · (gpt) | UI/React fluency |
| **Bulk coder** | opencode · deepseek | cheap high-volume code |
| **Analyst** | agy · gemini-flash (big ctx) | reads the WHOLE repo cheaply |
| **QA** | agy · gemini / claude-via-agy | tests, security, second eye |
| **GitHub ops** | copilot · gpt | PRs, issues, releases (its strength) |
| *(future)* | vercel / railway / supabase specialists | each has its own plugins+MCP |

Gateway note: agy exposes **Gemini Flash/Pro AND Claude Opus/Sonnet 4.6 AND
GPT-OSS**; copilot exposes GPT-family + BYOK. So "Claude" can run through agy on a
DIFFERENT quota than the main subscription — key for fallback.

### What the Analyst actually does (was unclear)
The Analyst is the team's **eyes**. On a big/unfamiliar repo, the supervisor and
coders would burn tokens reading files one by one. Instead:
1. Analyst (Gemini, huge context) reads the whole repo in one pass.
2. Produces a **reference map**: modules, data flow, "where is X / who calls it /
   what breaks if changed", plus the sequence diagram.
3. **Indexes that map into lean-ctx** so every worker can read the project's
   shape cheaply, instead of re-reading source. (Open question: exact lean-ctx
   write path — needs a spike.)
Skip it for small, already-understood changes — it's overhead there.

## 3. Token-limit master

**What each engine exposes (measured, not guessed):**

| Engine | Limit signal | Quality |
|--------|--------------|---------|
| **claude** | `-p --output-format=stream-json` → `rate_limit_info`: `status` (allowed / allowed_warning / rejected), `utilization` (0–1), `rateLimitType`, `resetsAt`, `unifiedWindows` (five_hour + seven_day) | **proactive** — see it coming |
| codex | `exec --json` → per-turn `usage` tokens; no quota remaining | reactive only |
| agy / gemini | server-side quota, nothing local | reactive (catch 429) |
| copilot | nothing local | reactive |

So: **proactive for claude** (the scarcest, most-watched resource — lucky), and
**reactive for the rest** (act when a worker returns a limit error).

**Behavior:**
- **Planning:** claude's `utilization` + `resetsAt` tell the planner how much
  Claude budget is left this window. Plan Claude-heavy tasks accordingly; if the
  seven_day window is near full, route reasoning to agy-Claude or Gemini Pro.
- **Execution:** after each claude turn, read `rate_limit_info`. On
  `status: rejected` (or `utilization` past a threshold), **swap** that role to a
  fallback engine/model and note it. On any worker's limit error, reassign the
  same task to a capable, non-limited peer (this rule already exists in the
  supervisor prompt — token-master makes it data-driven).
- **Fallback ladder** (example): claude-opus → agy(claude-opus-4-6) →
  agy(gemini-3.1-pro) → codex. Configurable.

**Reality check:** we CANNOT know remaining quota for codex/agy/copilot without
hitting a 429 — no local counter. cao-tokens shows spend, not the ceiling. So
budget-planning is exact for Claude, approximate elsewhere.

## 4. Task planner (enrich tasks.json)

Today tasks.json has: id, title, detail, engine, files, depends_on, status.
Add, for planning + monitoring:

```jsonc
{
  "id": "t3",
  "title": "…", "detail": "…",
  "role": "bulk_coder",           // the function
  "engine": "coder_worker",       // the profile that runs it
  "model": "deepseek-…",          // the model chosen (planner/token-master)
  "files": ["…"], "depends_on": ["t2"],
  "status": "pending|running|done|blocked",
  "created_at": "2026-09-19T…",   // when planned
  "started_at": null, "done_at": null,
  "comments": [                   // supervisor / worker notes over time
    {"by": "supervisor", "at": "…", "text": "…"}
  ],
  "qa": {"verdict": "pass|blocker|none", "by": "antigravity_worker", "notes": "…"}
}
```

Planner writes the list up front (role+engine+model per task from the template +
budgets). token-master may rewrite `engine`/`model` as limits change; every swap
appends a comment.

## 5. cao-monitor (like cao-tokens, for tasks)

Reads `cao_session/*/tasks.json` and shows the board:
- **status + executor**: id, title, status, role, engine·model
- **timestamps**: created / started / done + duration
- **comments + QA**: latest comment, QA verdict (pass/blocker)
- **`--watch`**: live auto-refresh (top/htop style)
Read-only. One project's board, or all.

## 6. Multi-project (open question)

`cao-run` hardcodes session-name `supervisor` → tmux `cao-supervisor`, so only
one at a time. `cao launch` accepts any `--session-name` + `--working-directory`,
so per-project is feasible: name the session from the project (`cao-<project>`),
and `cao-stop` still finds them all by the `cao-` prefix. Cost: more tmux
sessions (one supervisor + its workers per project). Plain Claude has no such
tmux overhead, but cao needs the daemon+tmux for orchestration — that's the price
of multi-agent. Decision deferred.

---

## Build order (proposed)

1. **cao-limits** — read limits from every engine (claude fully, others best-effort). Foundation for token-master.
2. **Role template + agy-Claude fallback** — set the defaults; make the supervisor fall back to agy-Claude when the main Claude window is spent.
3. **Planner** — enrich tasks.json (role/model/timestamps/comments/qa) + supervisor prompt to plan up front.
4. **cao-monitor** — the board viewer (`--watch`).
5. **token-master loop** — wire cao-limits into planning + execution swaps.
6. **Multi-project** + specialist workers (vercel/railway/supabase) — last.

Open spikes: analyst→lean-ctx index path; codex/agy/copilot reactive-limit
detection strings; per-model prefix handling in render (opencode-only prefix
already fixed).
