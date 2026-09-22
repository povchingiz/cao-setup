"""cao_tamper — Anti-Test-Tampering Gate.

Prevents autonomous workers and self-healing loops from cheating tests by
weakening assertions, deleting test cases, or inserting bypasses into tests/.
"""
import re
import subprocess
from pathlib import Path
from typing import List, Tuple


SUSPICIOUS_DIFF_PATTERNS = [
    (r"^-.*(assert\s|self\.assert|expect\()", "Deleted test assertion"),
    (r"^-.*def\s+test_", "Deleted test case function"),
    (r"^\+.*pytest\.skip\(", "Inserted pytest.skip bypass"),
    (r"^\+.*assert\s+True\b", "Inserted dummy assert True"),
]


def detect_test_tampering(repo_root: Path) -> Tuple[bool, str, List[str]]:
    """Inspect git diff for modifications to tests/ that weaken or delete assertions.

    Returns:
        (is_tampered, message, list_of_tampered_files)
    """
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return False, "", []

    try:
        # Check if git is available and repo has changes in tests/
        cmd = ["git", "diff", "--unified=0", "--", "tests/"]
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return False, "", []

        diff_text = proc.stdout
        tampered_files = set()
        violations = []
        current_file = ""

        for line in diff_text.splitlines():
            if line.startswith("--- a/"):
                current_file = line[6:].strip()
            elif line.startswith("+++ b/"):
                current_file = line[6:].strip()

            for pattern, reason in SUSPICIOUS_DIFF_PATTERNS:
                if re.search(pattern, line):
                    tampered_files.add(current_file)
                    violations.append(f"{current_file}: {reason} (`{line.strip()}`)")

        if violations:
            msg = "Test tampering detected:\n" + "\n".join(f"- {v}" for v in violations)
            return True, msg, sorted(list(tampered_files))

        return False, "", []

    except Exception as exc:
        # If git check fails, do not block execution
        return False, f"Tamper check warning: {exc}", []


def revert_test_tampering(repo_root: Path, tampered_files: List[str]) -> bool:
    """Revert changes to tampered test files via git checkout."""
    if not tampered_files:
        return True

    try:
        cmd = ["git", "checkout", "--"] + tampered_files
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except Exception:
        return False
