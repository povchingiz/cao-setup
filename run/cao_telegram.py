"""Telegram notification helper for CAO telemetry and alerts.

Zero external dependencies (uses standard library urllib). Reads:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
from the environment or falls back gracefully without error.
"""
import json
import os
import sys
import urllib.request
import urllib.error

ICONS = {
    "info": "ℹ️",
    "warn": "⚠️",
    "block": "🚨",
    "success": "✅",
    "error": "❌",
}


def notify_telegram(text: str, level: str = "info") -> bool:
    """Send a markdown notification to the configured Telegram chat.

    Returns True if successfully sent, False if credentials are missing
    or network failure occurred.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    icon = ICONS.get(level.lower(), "ℹ️")
    formatted = f"{icon} {text}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": formatted,
            "parse_mode": "Markdown",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"WARN: Telegram notification failed: {exc}", file=sys.stderr)
        return False
