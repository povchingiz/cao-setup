"""cao_skills — Dynamic Procedural Memory Manager.

Saves and retrieves learned procedural skills in wcao/skills/<topic>.md so agents
can record repeatable workflows, framework quirks, and audit lessons.
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def sanitize_topic(topic: str) -> str:
    """Convert topic into a safe filename slug."""
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", topic.strip().lower()).strip("_")
    return slug or "untitled_skill"


def get_skills_dir(repo_root: Optional[Path] = None) -> Path:
    """Resolve and ensure wcao/skills/ directory exists."""
    if repo_root is None:
        from run.cao_auto import find_repo_root
        repo_root = find_repo_root(Path.cwd())
    skills_dir = repo_root / "wcao" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def save_skill(
    topic: str,
    content: str,
    repo_root: Optional[Path] = None,
    tags: Optional[List[str]] = None,
) -> Path:
    """Save a learned procedural skill into wcao/skills/<topic>.md."""
    skills_dir = get_skills_dir(repo_root)
    slug = sanitize_topic(topic)
    file_path = skills_dir / f"{slug}.md"

    now_iso = datetime.now(timezone.utc).isoformat()
    tags_str = ", ".join(tags) if tags else "procedural"

    formatted = f"""---
title: "{topic}"
tags: [{tags_str}]
created_at: "{now_iso}"
---

# {topic}

{content.strip()}
"""
    file_path.write_text(formatted, encoding="utf-8")
    return file_path


def load_skill(topic: str, repo_root: Optional[Path] = None) -> Optional[str]:
    """Load skill content by topic or slug."""
    skills_dir = get_skills_dir(repo_root)
    slug = sanitize_topic(topic)
    file_path = skills_dir / f"{slug}.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def list_skills(repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all procedural skills recorded in wcao/skills/."""
    skills_dir = get_skills_dir(repo_root)
    results = []
    for f in sorted(skills_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        results.append({
            "topic": f.stem,
            "path": str(f),
            "preview": text[:200].replace("\n", " "),
        })
    return results


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: cao_skills.py [list | save <topic> <content> | load <topic>]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        for s in list_skills():
            print(f"- {s['topic']}: {s['path']}")
    elif cmd == "save" and len(sys.argv) >= 4:
        topic = sys.argv[2]
        content = sys.argv[3]
        p = save_skill(topic, content)
        print(f"✓ Saved skill: {p}")
    elif cmd == "load" and len(sys.argv) >= 3:
        content = load_skill(sys.argv[2])
        if content:
            print(content)
        else:
            print(f"Skill '{sys.argv[2]}' not found.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
