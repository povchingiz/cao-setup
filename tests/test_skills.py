import pytest
from pathlib import Path
from run.cao_skills import sanitize_topic, save_skill, load_skill, list_skills


def test_sanitize_topic():
    assert sanitize_topic("Node 22 Strip Types") == "node_22_strip_types"
    assert sanitize_topic("special!@#chars") == "special_chars"
    assert sanitize_topic("") == "untitled_skill"


def test_save_and_load_skill(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    topic = "Poetry Pytest Runner"
    content = "Always run tests using `poetry run pytest -q`."
    path = save_skill(topic=topic, content=content, repo_root=repo, tags=["testing", "poetry"])

    assert path.exists()
    assert "poetry_pytest_runner.md" in path.name

    loaded = load_skill(topic, repo_root=repo)
    assert loaded is not None
    assert "Always run tests using `poetry run pytest -q`." in loaded
    assert 'tags: [testing, poetry]' in loaded


def test_list_skills(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    save_skill("Skill One", "First lesson", repo_root=repo)
    save_skill("Skill Two", "Second lesson", repo_root=repo)

    skills = list_skills(repo_root=repo)
    assert len(skills) == 2
    topics = [s["topic"] for s in skills]
    assert "skill_one" in topics
    assert "skill_two" in topics
