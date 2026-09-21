# cao-limits — engine quota status tool (design spec)

> **Status:** Approved 2026-09-19. First tool in the CAO v2 build order.
> **Depends on:** nothing new (reads existing on-disk data).
> **Feeds into:** token-master (v2 step 5), potentially cao-doctor D5.

---

## 1. Purpose

`cao-tokens` answers "how much did I spend?". `cao-limits` answers
"how much is left?" — or as close as each engine allows.

The tool is the **data foundation** for the token-master loop that will
reassign engines during planning and execution when quotas run thin.

## 2. Scope (this step only)

- **Report measurable limit signals** — no active probing, no API calls.
- **Claude:** parse the latest `rate_limit_info` from existing session
  logs (`~/.claude/projects/**/*.jsonl`). Claude writes this every turn;
  we read the most recent entry.
- **Codex:** spend totals from SQLite (no ceiling data exists locally).
- **Opencode:** spend + real $ cost from SQLite (no ceiling data).
- **Agy/Gemini:** nothing local — noted as server-side only.
- **No user-configurable budget ceilings** (deferred to token-master).

## 3. Interfaces

### 3.1 CLI (`cao-limits`)

Default human-readable output:

```
cao-limits — engine quota status

CLAUDE (last seen 3 min ago)
├─ 5-hour window:  ░░░░░░░▓▓▓  utilization 0.31  allowed     resets 2026-09-19T22:45:00Z
└─ 7-day  window:  ░░░░░░░░▓█  utilization 0.89  ⚠ warning   resets 2026-09-22T00:00:00Z

CODEX
└─ spend: 45.2k tokens (no local ceiling data)

OPENCODE
└─ spend: 128.7k tokens  $0.42 (no local ceiling data)

AGY / GEMINI
└─ (no local usage log — quota is server-side)
```

Flags:
- `--json` — machine-readable JSON
- `--claude` — Claude detail only
- `--cao-only` / `--all-sessions` — same CAO-session filter as `cao-tokens` (default: cao-only)
- `-h` / `--help`

### 3.2 JSON output (`--json`)

```json
{
  "claude": {
    "stale_seconds": 180,
    "five_hour": {
      "utilization": 0.31,
      "status": "allowed",
      "resets_at": "2026-09-19T22:45:00Z"
    },
    "seven_day": {
      "utilization": 0.89,
      "status": "allowed_warning",
      "resets_at": "2026-09-22T00:00:00Z"
    }
  },
  "codex": { "tokens_used": 45200 },
  "opencode": { "tokens_in": 80000, "tokens_out": 48700, "cost": 0.42 },
  "agy": null
}
```

### 3.3 Python API (`cao_limits.get_limits`)

```python
from cao_limits import get_limits

report = get_limits(cao_only=True)

# Claude windows
report.claude.seven_day.utilization   # 0.89
report.claude.seven_day.status        # "allowed_warning"
report.claude.seven_day.resets_at     # "2026-09-22T00:00:00Z"
report.claude.stale_seconds           # 180 (seconds since last data point)

# Convenience
report.claude.is_near_limit()         # True  (utilization > 0.8 or status == "allowed_warning")
report.claude.is_blocked()            # False (status != "rejected")

# Other engines (spend only)
report.codex.tokens_used              # 45200
report.opencode.tokens_in             # 80000
report.opencode.tokens_out            # 48700
report.opencode.cost                  # 0.42
report.agy                            # None
```

## 4. Claude rate-limit data (real format, verified from disk)

Claude writes rate-limit data in **two places**, both useful:

### 4a. Proactive warning (`rate_limit_event`) — in `tool-results/*.txt`

Found in `~/.claude/projects/<project>/<session_id>/tool-results/*.txt`.
Written when utilization crosses a threshold (e.g. 75%).

```json
{
  "type": "rate_limit_event",
  "rate_limit_info": {
    "status": "allowed_warning",
    "resetsAt": 1790146800,
    "rateLimitType": "seven_day",
    "utilization": 0.89,
    "isUsingOverage": false,
    "surpassedThreshold": 0.75,
    "unifiedWindows": {
      "five_hour": { "utilization": 0.55, "resetsAt": 1789851600 },
      "seven_day": { "utilization": 0.89, "resetsAt": 1790146800 }
    }
  },
  "uuid": "...",
  "session_id": "..."
}
```

### 4b. Hard rejection (`quotaLimits`) — in main session jsonl

Written when Claude hits 429 (session/daily limit exhausted).
Lives in `~/.claude/projects/<project>/<session_id>.jsonl`.

```json
{
  "timestamp": "2026-09-19T15:13:50.835Z",
  "quotaLimits": {
    "status": "rejected",
    "resetsAt": 1789833000,
    "rateLimitType": "five_hour",
    "overageStatus": "rejected",
    "overageDisabledReason": "out_of_credits",
    "isUsingOverage": false
  },
  "error": "rate_limit",
  "apiErrorStatus": 429,
  "message": { "content": [{"text": "You've hit your session limit · resets ..."}] }
}
```

### Key facts

- `resetsAt` is a **Unix timestamp** (seconds), not ISO.
- `unifiedWindows` (with `utilization` per window) is only in the
  proactive `rate_limit_event`, not in the 429 rejection.
- The 429 rejection has `rateLimitType` ("five_hour") but no utilization
  or unified windows — it's binary (blocked or not).
- Both sources are CAO-filterable (by session_id presence in CAO sessions).

### Strategy

1. Scan `tool-results/*.txt` files under all recent Claude session dirs
   for `rate_limit_event` entries → extract `unifiedWindows` with
   per-window utilization.
2. Scan main `.jsonl` files for `quotaLimits` entries with
   `error: "rate_limit"` → extract rejection status and `resetsAt`.
3. Use the **most recent** data point from either source.
4. If a `rate_limit_event` and a `quotaLimits` rejection both exist,
   the rejection is the stronger signal (report both, flag as blocked).
5. If neither exists, Claude section reports `null` (no data yet).

## 5. File structure

| File | What |
|------|------|
| `run/cao_lib.py` | Shared helpers extracted from `cao-tokens`: `_q()` (sqlite), `_iter_claude_files()`, `_file_is_cao()`, `hn()`, `cutoff_ts()` |
| `run/cao_limits.py` | Core module: dataclasses, `get_limits()`, claude rate-limit parser |
| `run/cao-limits` | CLI entry point (thin: parse args → call `get_limits()` → format) |
| `run/cao-tokens` | Refactored to import from `cao_lib.py` (drop duplicate helpers) |

After `apply.sh` / bootstrap, `cao-limits` is symlinked into
`~/.local/bin/` alongside the other tools.

## 6. Non-goals (deferred)

- Active Claude probing (firing `claude -p` to get fresh data).
- User-configurable budget ceilings per engine.
- Automatic engine swapping (token-master loop).
- Integration into `cao-doctor` D5.
- Reactive 429 detection for codex/agy/copilot.

These are all token-master (step 5) or later.

## 7. Testing

- Unit: mock claude jsonl with `rate_limit_info` lines → verify parsing.
- Unit: mock sqlite dbs → verify spend aggregation.
- Integration: run `cao-limits` on the real machine, verify output matches
  `cao-tokens` spend numbers and Claude's actual limit state.
- Edge: no claude sessions exist → `claude: null`.
- Edge: `rate_limit_info` with `status: rejected` → `is_blocked()` returns True.
