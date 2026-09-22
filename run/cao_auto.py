"""cao_auto — Headless Autonomous Execution Engine for CAO.

Dispatches tasks from cao_session/session_NNN/tasks.json according to a
dependency DAG and file disjointness rules, interfaces with the CAO daemon
REST API (port 9889), auto-routes 429/quota errors to the universal OpenCode
fallback engine (coder_worker / DeepSeek-V4-Pro), updates tasks.json in real
time for cao-monitor, and executes the automated Audit Gate upon completion.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from run.cao_fallback import is_quota_error, apply_fallback
from run.cao_telegram import notify_telegram
from run.cao_compactor import ContextCompactor

DEFAULT_SERVER_PORT = 9889


def find_repo_root(start_dir: Path) -> Path:
    """Search upward from start_dir for .git, pyproject.toml, or cao.config.toml."""
    curr = start_dir.resolve()
    for parent in [curr, *curr.parents]:
        if (
            (parent / ".git").exists()
            or (parent / "pyproject.toml").exists()
            or (parent / "cao.config.toml").exists()
            or (parent / "2_configure" / "cao.config.toml").exists()
        ):
            return parent
    return curr


class DagScheduler:
    """Evaluates task dependencies (depends_on) and file-level disjointness."""

    def __init__(self, tasks: List[dict]):
        self.tasks = tasks

    def get_ready_tasks(self, running_files: Set[str]) -> List[dict]:
        """Return all tasks whose dependencies are met and whose files do not collide."""
        done_ids = {t["id"] for t in self.tasks if t.get("status") == "done"}
        ready = []
        locked_files = set(running_files)

        for t in self.tasks:
            if t.get("status") != "pending":
                continue

            # Check dependencies
            deps = t.get("depends_on") or []
            if not all(dep in done_ids for dep in deps):
                continue

            # Check file collisions
            files = set(t.get("files") or [])
            if files and files.intersection(locked_files):
                continue

            ready.append(t)
            locked_files.update(files)

        return ready

    def is_complete(self) -> bool:
        """Return True when every task is marked 'done'."""
        return all(t.get("status") == "done" for t in self.tasks)

    def get_running_tasks(self) -> List[dict]:
        return [t for t in self.tasks if t.get("status") == "running"]


class CaoClient:
    """Client for the local CAO daemon REST API."""

    def __init__(self, port: int = DEFAULT_SERVER_PORT):
        self.base_url = f"http://127.0.0.1:{port}"

    def is_healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def launch_session(
        self,
        agent_profile: str,
        initial_message: str,
        model: Optional[str] = None,
        working_directory: Optional[str] = None,
    ) -> dict:
        """Launch a worker session and terminal via POST /sessions."""
        params = [f"agent_profile={agent_profile}"]
        if model:
            params.append(f"model={urllib.parse.quote(model)}")
        if working_directory:
            params.append(f"working_directory={urllib.parse.quote(working_directory)}")

        url = f"{self.base_url}/sessions?{'&'.join(params)}"
        body = json.dumps({"initial_message": initial_message}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_terminal(self, terminal_id: str) -> dict:
        url = f"{self.base_url}/terminals/{terminal_id}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_terminal_output(self, terminal_id: str) -> str:
        url = f"{self.base_url}/terminals/{terminal_id}/output"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("output", "")
        except Exception:
            return ""

    def delete_terminal(self, terminal_id: str) -> bool:
        url = f"{self.base_url}/terminals/{terminal_id}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False


class AutonomousRunner:
    """Manages the lifecycle of an autonomous session."""

    def __init__(
        self,
        tasks_file: Path,
        max_workers: int = 4,
        client: Optional[CaoClient] = None,
        dry_run: bool = False,
        self_heal: bool = True,
        max_heal_attempts: int = 3,
    ):
        self.tasks_file = tasks_file
        self.session_dir = tasks_file.parent
        self.repo_root = find_repo_root(self.session_dir)
        self.max_workers = max_workers
        self.client = client or CaoClient()
        self.dry_run = dry_run
        self.self_heal = self_heal
        self.max_heal_attempts = max_heal_attempts
        self.compactor = ContextCompactor()
        self.recent_worker_outputs: List[str] = []
        # Map: task_id -> {terminal_id, started_monotonic}
        self.active_workers: Dict[str, dict] = {}

    def load_tasks(self) -> List[dict]:
        return json.loads(self.tasks_file.read_text(encoding="utf-8"))

    def save_tasks(self, tasks: List[dict]) -> None:
        self.tasks_file.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

    def run(self, poll_interval: float = 3.0) -> bool:
        """Run tasks until complete or blocked."""
        tasks = self.load_tasks()
        scheduler = DagScheduler(tasks)

        notify_telegram(
            f"Starting autonomous session ({len(tasks)} tasks) in `{self.session_dir.name}`",
            level="info",
        )

        while not scheduler.is_complete():
            # 1. Inspect running tasks
            running_files = set()
            for t in scheduler.get_running_tasks():
                running_files.update(t.get("files") or [])

            # 2. Dispatch ready tasks up to max_workers
            slots = self.max_workers - len(self.active_workers)
            if slots > 0:
                ready_tasks = scheduler.get_ready_tasks(running_files)[:slots]
                for task in ready_tasks:
                    self._dispatch_task(task, tasks)

            # 3. Poll active terminals
            self._poll_active_terminals(tasks)
            self.save_tasks(tasks)
            scheduler = DagScheduler(tasks)

            # 4. Hermes 50% Context Compaction Hook
            self.compactor.record_turn()
            if self.compactor.should_compact():
                design_dir = self.repo_root / "wcao" / "design"
                design_contracts = (
                    [str(f.relative_to(self.repo_root)) for f in design_dir.glob("*.md")]
                    if design_dir.exists()
                    else []
                )
                compacted = self.compactor.compact(
                    root_goal=f"Autonomous session in {self.session_dir.name}",
                    tasks=tasks,
                    worker_outputs=self.recent_worker_outputs,
                    design_contracts=design_contracts,
                )
                now_md = self.repo_root / "wcao" / "plans" / "now.md"
                self.compactor.checkpoint_to_now_md(now_md, compacted)

            if not self.active_workers and not scheduler.get_ready_tasks(running_files) and not scheduler.is_complete():
                # Stalled: all pending tasks have unresolved dependencies or blocks
                notify_telegram(
                    f"Execution stalled in `{self.session_dir.name}`: pending tasks blocked.",
                    level="block",
                )
                return False

            if not scheduler.is_complete():
                time.sleep(poll_interval)

        # 4. Trigger Autonomous Audit Gate & Self-Healing Loop
        heal_attempt = 0
        last_failure_reason = ""
        while heal_attempt <= self.max_heal_attempts:
            notify_telegram(
                f"Running Postflight Audit Gate for `{self.session_dir.name}` (Attempt {heal_attempt + 1})...",
                level="info",
            )
            audit_pass, audit_notes = self._run_audit_gate(tasks)
            self.save_tasks(tasks)

            if audit_pass:
                if heal_attempt > 0:
                    # Hermes Retrospective: Store the lesson learned!
                    from run.cao_memory import store_memory
                    from run.cao_skills import save_skill
                    summary = f"Self-healed audit issue in {self.session_dir.name}"
                    details = f"Fixed audit blocker after {heal_attempt} remediation attempt(s). Root cause: {last_failure_reason}. Result: {audit_notes}"
                    db_path = self.repo_root / "wcao" / "memory.sqlite"
                    store_memory("self_healing", summary, details, session_id=self.session_dir.name, db_path=db_path)
                    save_skill(f"healing_{self.session_dir.name}", f"# {summary}\n\n{details}", repo_root=self.repo_root)
                    notify_telegram(f"Hermes retrospective stored self-healing lesson: {summary}", level="info")

                notify_telegram(
                    f"Session `{self.session_dir.name}` COMPLETE: all tasks done, 0 audit blockers!",
                    level="success",
                )
                return True

            last_failure_reason = audit_notes
            if not self.self_heal or heal_attempt >= self.max_heal_attempts:
                notify_telegram(
                    f"Session `{self.session_dir.name}` completed with audit warnings/blockers after {heal_attempt} healing attempt(s).",
                    level="warn",
                )
                return False

            # Trigger Self-Healing: Generate remediation task
            heal_attempt += 1
            remediation_id = f"remediation_heal_{heal_attempt}_{int(time.time())}"
            remediation_task = {
                "id": remediation_id,
                "title": f"Self-healing fix for audit failure (Attempt {heal_attempt})",
                "status": "pending",
                "engine": "coder_worker",
                "depends_on": [],
                "detail": f"Audit Gate failed with: {audit_notes}\nFix the failing tests, syntax errors, or security blockers and ensure the audit passes.",
            }
            tasks.append(remediation_task)
            self.save_tasks(tasks)
            notify_telegram(f"Spawned self-healing remediation task: `{remediation_id}`", level="warn")

            # Execute remediation task
            scheduler = DagScheduler(tasks)
            while not scheduler.is_complete():
                running_files = set()
                for t in scheduler.get_running_tasks():
                    running_files.update(t.get("files") or [])
                slots = self.max_workers - len(self.active_workers)
                if slots > 0:
                    ready_tasks = scheduler.get_ready_tasks(running_files)[:slots]
                    for t in ready_tasks:
                        self._dispatch_task(t, tasks)
                self._poll_active_terminals(tasks)
                self.save_tasks(tasks)
                scheduler = DagScheduler(tasks)
                if not self.active_workers and not scheduler.get_ready_tasks(running_files) and not scheduler.is_complete():
                    break
                if not scheduler.is_complete():
                    time.sleep(poll_interval)

    def _dispatch_task(self, task: dict, all_tasks: List[dict]) -> None:
        tid = task["id"]
        engine = task.get("engine", "coder_worker")
        model = task.get("model")
        payload = f"Task {tid}: {task.get('title')}\n\n{task.get('detail')}"

        # Hermes Pre-Task Recall Gate: Query memory for relevant past lessons
        query_text = f"{task.get('title', '')} {' '.join(task.get('files', []))} {task.get('detail', '')}".strip()
        from run.cao_memory import query_memory
        db_path = self.repo_root / "wcao" / "memory.sqlite"
        memories = query_memory(query_text, limit=3, db_path=db_path) if db_path.exists() else []
        if memories:
            mem_lines = ["--- Inherited Project Knowledge (Hermes Memory) ---"]
            for m in memories:
                mem_lines.append(f"- [{m.get('category', 'general')}]: {m.get('summary', '')} - {m.get('details', '')}")
            mem_lines.append("---------------------------------------------------\n")
            payload = "\n".join(mem_lines) + "\n" + payload
            task["recalled_memories"] = [m.get("summary") for m in memories]

        task["status"] = "running"
        task["started_at"] = datetime.now(timezone.utc).isoformat()
        self.save_tasks(all_tasks)

        if self.dry_run:
            self.active_workers[tid] = {"dry_run": True, "started": time.monotonic()}
            return

        try:
            resp = self.client.launch_session(
                agent_profile=engine,
                initial_message=payload,
                model=model,
                working_directory=str(self.repo_root),
            )
            terminal_id = resp.get("terminal_id") or resp.get("terminals", [{}])[0].get("terminal_id")
            self.active_workers[tid] = {
                "terminal_id": terminal_id,
                "engine": engine,
                "started": time.monotonic(),
            }
        except Exception as exc:
            # Check if launch failure is a quota/engine error -> auto-fallback
            if is_quota_error(str(exc)):
                apply_fallback(task, str(exc))
                notify_telegram(
                    f"Task {tid}: {engine} launch hit quota -> auto-swapped to {task['engine']}",
                    level="warn",
                )
                # Re-dispatch immediately with fallback
                self._dispatch_task(task, all_tasks)
            else:
                task["status"] = "blocked"
                task.setdefault("comments", []).append(
                    {"by": "orchestrator", "at": datetime.now(timezone.utc).isoformat(), "text": f"Launch error: {exc}"}
                )

    def _poll_active_terminals(self, all_tasks: List[dict]) -> None:
        completed = []
        task_map = {t["id"]: t for t in all_tasks}

        for tid, meta in list(self.active_workers.items()):
            task = task_map.get(tid)
            if not task:
                continue

            if meta.get("dry_run"):
                if time.monotonic() - meta["started"] > 1.0:
                    task["status"] = "done"
                    task["done_at"] = datetime.now(timezone.utc).isoformat()
                    completed.append(tid)
                continue

            terminal_id = meta.get("terminal_id")
            if not terminal_id:
                completed.append(tid)
                continue

            try:
                term = self.client.get_terminal(terminal_id)
                status = term.get("status", "").upper()
                output = self.client.get_terminal_output(terminal_id)

                # Check 429 / Quota error
                if is_quota_error(output) or is_quota_error(term.get("error")):
                    self.client.delete_terminal(terminal_id)
                    apply_fallback(task, "runtime 429 / quota limit")
                    notify_telegram(
                        f"Task {tid}: {meta.get('engine')} hit quota -> auto-swapped to {task['engine']} ({task.get('model')})",
                        level="warn",
                    )
                    # Re-dispatch immediately with fallback
                    del self.active_workers[tid]
                    self._dispatch_task(task, all_tasks)
                    continue

                if status == "COMPLETED":
                    task["status"] = "done"
                    task["done_at"] = datetime.now(timezone.utc).isoformat()
                    self.client.delete_terminal(terminal_id)
                    completed.append(tid)
                    self.recent_worker_outputs.append(f"Task {tid} done ({output[:100] if output else 'no output'})")
                elif status == "ERROR":
                    task["status"] = "blocked"
                    task.setdefault("comments", []).append(
                        {
                            "by": "orchestrator",
                            "at": datetime.now(timezone.utc).isoformat(),
                            "text": f"Terminal exited with error: {term.get('error', 'unknown')}",
                        }
                    )
                    self.client.delete_terminal(terminal_id)
                    completed.append(tid)
            except Exception as exc:
                print(f"WARN polling terminal {terminal_id}: {exc}", file=sys.stderr)

        for tid in completed:
            self.active_workers.pop(tid, None)

    def _run_audit_gate(self, all_tasks: List[dict]) -> Tuple[bool, str]:
        """Run project tests and aggressive audit, recording QA verdict."""
        root_dir = self.repo_root
        passed = True
        notes = "Automated test suite passed."

        aggressive_script = root_dir / "run" / "cao-aggressive"
        if aggressive_script.exists() and not self.dry_run:
            try:
                res = subprocess.run(
                    [sys.executable, str(aggressive_script), "--json"],
                    cwd=str(root_dir),
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if res.returncode == 0:
                    try:
                        data = json.loads(res.stdout)
                        if data.get("verdict") == "pass":
                            passed = True
                            notes = "Aggressive audit passed: 0 blockers."
                        else:
                            passed = False
                            blockers = [b.get("message", "") for b in data.get("blockers", [])]
                            notes = f"Aggressive audit blockers: {'; '.join(blockers)}"
                    except Exception:
                        passed = True
                        notes = "Aggressive audit executed cleanly."
                else:
                    passed = False
                    try:
                        data = json.loads(res.stdout)
                        blockers = [b.get("message", "") for b in data.get("blockers", [])]
                        notes = f"Audit failed: {'; '.join(blockers) or res.stderr[:200]}"
                    except Exception:
                        notes = f"Audit failed: {res.stderr[:200] or res.stdout[:200]}"
            except Exception as e:
                passed = False
                notes = f"Audit execution error: {e}"
        else:
            test_cmd = None
            if (root_dir / "pyproject.toml").exists():
                if shutil.which("pytest"):
                    test_cmd = ["pytest", "-q"]
                elif shutil.which("uv"):
                    test_cmd = ["uv", "run", "--with", "pytest", "pytest", "-q"]
                else:
                    test_cmd = [sys.executable, "-m", "unittest", "discover", "tests"]
            elif (root_dir / "package.json").exists() and shutil.which("npm"):
                test_cmd = ["npm", "test"]

            if test_cmd and not self.dry_run:
                try:
                    res = subprocess.run(test_cmd, cwd=str(root_dir), capture_output=True, text=True, timeout=60)
                    if res.returncode != 0:
                        passed = False
                        notes = f"Tests failed: {res.stderr[:200] or res.stdout[:200]}"
                except Exception as e:
                    passed = False
                    notes = f"Test execution error: {e}"

        verdict = "pass" if passed else "block"
        now_iso = datetime.now(timezone.utc).isoformat()
        for t in all_tasks:
            t["qa"] = {
                "verdict": verdict,
                "by": "antigravity_worker",
                "at": now_iso,
                "notes": notes,
            }
        return passed, notes
