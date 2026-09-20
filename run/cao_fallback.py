"""Quota & 429 Fallback Engine for CAO tasks.

Detects quota exhaustion and rate limit signatures in terminal output,
and mutates task dictionaries to point to the universal fallback engine
(coder_worker with DeepSeek-V4-Pro) while appending structured comments.
"""
import re
from datetime import datetime, timezone
from typing import Optional

QUOTA_PATTERNS = [
    r"\b429\b",
    r"rate\s*limit",
    r"quota\s*exceeded",
    r"usage\s*limit",
    r"insufficient\s*credits",
    r"credit\s*balance",
    r"resource\s*has\s*been\s*exhausted",
    r"overloaded",
    r"provider\s*response\s*headers\s*timed\s*out",
]


def is_quota_error(text: Optional[str]) -> bool:
    """Return True if text contains a rate-limit, quota, or timeout signature."""
    if not text:
        return False
    return any(re.search(pat, text, re.IGNORECASE) for pat in QUOTA_PATTERNS)


def apply_fallback(task: dict, reason: str = "quota/429") -> dict:
    """Mutate task to use its fallback engine and model, recording the event."""
    prev_engine = task.get("engine", "unknown")
    fallback_eng = task.get("fallback_engine", "coder_worker")
    fallback_mod = task.get("fallback_model", "deepseek-ai/DeepSeek-V4-Pro")

    task["engine"] = fallback_eng
    task["model"] = fallback_mod

    comments = task.setdefault("comments", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    comment = {
        "by": "orchestrator",
        "at": now_iso,
        "text": f"Tier 1 limit on {prev_engine} ({reason}) -> auto-swapped to {fallback_eng} ({fallback_mod})",
    }
    comments.append(comment)
    return task
