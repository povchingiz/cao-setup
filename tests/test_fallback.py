from run.cao_fallback import is_quota_error, apply_fallback

def test_is_quota_error():
    assert is_quota_error("Error 429: rate limit exceeded") is True
    assert is_quota_error("quota exceeded for current billing window") is True
    assert is_quota_error("usage limit reached") is True
    assert is_quota_error("insufficient credits in account") is True
    assert is_quota_error("SyntaxError: invalid syntax") is False
    assert is_quota_error("") is False

def test_apply_fallback():
    task = {
        "id": "t1",
        "title": "Core Contract",
        "engine": "claude_worker",
        "model": "claude-opus-4-8",
        "fallback_engine": "coder_worker",
        "fallback_model": "deepseek-ai/DeepSeek-V4-Pro",
        "comments": []
    }
    updated = apply_fallback(task, "rate limit 429")
    assert updated["engine"] == "coder_worker"
    assert updated["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert len(updated["comments"]) == 1
    assert "Tier 1 limit on claude_worker" in updated["comments"][0]["text"]
    assert "auto-swapped to coder_worker" in updated["comments"][0]["text"]
