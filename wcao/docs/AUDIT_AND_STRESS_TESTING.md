# CAO Aggressive Audit & Stress-Testing Engine

> **Comprehensive guide to the `cao-aggressive` multi-dimension code auditor, security gate, and auto-generated load/stress-testing harness.**

---

## 1. Overview

In multi-agent autonomous engineering, the biggest risk is **premature sign-off**: an AI agent declares victory the instant it writes code, without checking for syntax traps, hardcoded credentials, 12-factor violations, or running actual tests.

`cao-aggressive` is CAO's built-in postflight auditor and stress-test generator. It acts as an unyielding gatekeeper:
1. **Audits the codebase** across 5 distinct dimensions (Security, 12-Factor, AST Syntax, Tests, and Anti-Tampering).
2. **Generates project artifacts** in `wcao/audit/`, including an **executive scorecard**, **threat analysis**, and an **auto-generated executable load/stress-testing harness (`stress-test.sh`)**.
3. **Serves as the mandatory signoff gate** for the autonomous runner (`cao_auto.py`).

```
cao-aggressive
   │
   ├── 1. Security & Secrets Scanner (tokens, AWS keys, private keys)
   ├── 2. 12-Factor Cloud-Native Hygiene (config, dependencies, disposability)
   ├── 3. AST Syntax Compiler (all Python & shell files)
   ├── 4. Automated Test Suite Execution (pytest, npm test, cargo test)
   └── 5. Anti-Tamper Verification (AST diff watchdog via cao_tamper.py)
   │
   ▼
Generates wcao/audit/
   ├── aggressive-audit.md   ← Executive scorecard & passed gates
   ├── stress-test-plan.md   ← Concurrency, fuzzing, and failure vectors
   ├── stress-test.sh        ← Executable load/stress test harness (chmod +x)
   ├── weaknesses.md         ← Threat analysis & edge-case hazard report
   └── real-sequence-diagram.mmd ← Visual system interaction trace
```

---

## 2. The 5 Verification Vectors

### Vector 1: Security & High-Entropy Secrets
Scans every tracked file for leaked credentials before code can ever be committed:
- **API Keys & Tokens:** `api_key = "..."`, `token = "..."`
- **GitHub Personal Access Tokens:** `ghp_[0-9a-zA-Z]{36}`
- **Slack Tokens:** `xox[baprs]-...`
- **OpenAI Keys:** `sk-...`
- **AWS Credentials:** `AKIA[0-9A-Z]{16}`
- **Private Keys:** `-----BEGIN RSA/EC/OPENSSH/PRIVATE KEY-----`
- **Environment Exclusions:** Verifies that `.env` is present in `.gitignore`.

### Vector 2: 12-Factor App & Cloud-Native Hygiene
Audits the architectural cleanliness of the project against modern cloud-native standards:
- **Factor I (Codebase):** Confirms valid git version tracking.
- **Factor II (Dependencies):** Verifies explicit manifest (`pyproject.toml`, `requirements.txt`, `package.json`, `Cargo.toml`, or `go.mod`).
- **Factor III (Config):** Ensures base URLs and endpoint settings are configurable through environment variables.
- **Factor IX (Disposability):** Checks for signal handling (`SIGINT`, `SIGTERM`) and graceful shutdown routines.
- **Factor XI (Logs):** Ensures zero raw `.log` files are committed to version control.

### Vector 3: AST Compilation & Shell Syntax
Catches syntax errors and malformed code before runtime:
- **Python AST:** Parses every `.py` file using Python's native `ast.parse()`. Immediately flags `SyntaxError`, `IndentationError`, or unclosed brackets.
- **Silent Exception Traps:** Detects anti-patterns like bare `except: pass` or `except Exception: pass` that hide critical failures.
- **Shell Script Validation:** Validates all `.sh` scripts using `bash -n` to catch unquoted variables, broken syntax, or unclosed quotes.

### Vector 4: Real Test Suite Execution
Executes the native test runner of the project with real process exit-code validation:
- **Python:** Discovers and runs `pytest` (via `uv run` or active virtualenv).
- **Node.js:** Executes `npm test` if `package.json` contains a test script.
- **Rust / Go:** Runs `cargo test` or `go test ./...`.
- **Custom / Stress Harness:** Automatically runs `wcao/audit/stress-test.sh` if present.

### Vector 5: Anti-Test-Tampering AST Watchdog (`cao_tamper.py`)
Agents frequently cheat by weakening tests when their implementation fails. `cao_tamper.py`:
- Parses test files before and after the agent's turn.
- Detects if assertion counts decreased or if dummy bypasses (`assert True`) were added.
- **Automatically reverts** the tampered test file using `git checkout` and marks the task as failed.

---

## 3. Auto-Generated Audit & Load-Testing Artifacts

When `cao-aggressive` runs, it generates four actionable artifacts in `wcao/audit/`:

### 1. `wcao/audit/aggressive-audit.md` (Executive Scorecard)
Contains the high-level audit summary:
- Total blockers, warnings, and passed checks.
- Categorized checklist of all passed and failed gates.
- Direct links to generated diagrams and test plans.

### 2. `wcao/audit/stress-test-plan.md` (Stress Vectors)
A structured testing plan outlining the exact load and boundary vectors tailored to the repository:
1. **Concurrency & Contention Vectors:** Parallel CLI execution, worker saturation, and session resilience.
2. **Input Boundary & Fuzzing Vectors:** Malformed flags, invalid paths, missing environment variables, oversized context files (>2MB).
3. **Failure Injection & Quota Starvation:** Simulated HTTP 429 rate limits, abrupt daemon termination, and network dropouts.
4. **Prioritized Action Items:** Explicit `[P0 BLOCKER]` and `[P1 WARNING]` remediation items.

### 3. `wcao/audit/stress-test.sh` (Executable Load Harness)
An auto-generated, executable bash script (`chmod 755`) that you can run directly to stress-test your project:
```bash
./wcao/audit/stress-test.sh
```
It executes three distinct phases:
- **Phase 1: Input fuzzing & boundary flags:** Verifies all CLIs reject unknown flags and respond to `--help` cleanly.
- **Phase 2: Concurrency burst:** Spawns multiple parallel executions simultaneously (e.g. 5 concurrent CLI calls) to verify process locking and SQLite concurrency.
- **Phase 3: Syntax & AST stress:** Runs mass AST compilation across the repository.

### 4. `wcao/audit/weaknesses.md` (Threat Analysis)
Documents edge-case vulnerabilities, security gaps, and potential silent failures discovered during the audit, along with concrete remediation steps.

---

## 4. Usage & Commands

```bash
# Run standard aggressive audit on the current project
cao-aggressive

# Output machine-readable JSON (ideal for CI/CD pipelines)
cao-aggressive --json

# Run audit and suggest concrete automated fixes for flagged issues
cao-aggressive --fix

# Dispatch live CAO worker agents (antigravity_worker / analyst) for deep semantic review
cao-aggressive --with-agents

# Execute the generated load/stress test harness
./wcao/audit/stress-test.sh
```

---

## 5. Integration into the Autonomous Loop (`cao_auto.py`)

`cao-aggressive` is deeply integrated into CAO's autonomous execution engine:

1. **Task Execution:** A worker finishes implementing a sub-task from `wcao/tasks.json`.
2. **Post-Task Audit Gate:** `cao_auto` executes `cao-aggressive` against the touched files.
3. **Pass / Fail Gate:**
   - **PASS:** Task status transitions to `done`. File locks are released, unlocking downstream dependent tasks in the DAG.
   - **FAIL (Attempt 1):** The failure output is fed back to the worker for an automatic self-healing attempt.
   - **FAIL (Attempt 2+):** Escalates to an **L2 Architect** (`hermes_worker` or `claude_worker`). The error and lesson are permanently stored in `wcao/memory.sqlite` via Hermes retrospective memory.
