from unittest.mock import patch, MagicMock
from run.cao_telegram import notify_telegram

def test_telegram_skipped_when_no_token():
    with patch.dict("os.environ", {}, clear=True):
        assert notify_telegram("test message") is False

def test_telegram_sends_when_configured():
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "999"}):
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_open.return_value.__enter__.return_value = mock_resp
            assert notify_telegram("test message", level="warn") is True

def test_telegram_handles_network_error_gracefully():
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "999"}):
        with patch("urllib.request.urlopen", side_effect=Exception("network down")):
            assert notify_telegram("test message", level="error") is False
