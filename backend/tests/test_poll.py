"""Offline tests for backend/poll.py (the local polling runner)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for _path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402

import config  # noqa: E402
import poll  # noqa: E402
from firebase_client import FirebaseConfigError  # noqa: E402


class FakeApplicationBuilder:
    def __init__(self, built):
        self._built = built

    def token(self, _token):
        return self

    def concurrent_updates(self, _flag):
        return self

    def build(self):
        return self._built


class FakeApplication:
    def __init__(self):
        self.handlers_registered = False
        self.poll_kwargs = {}

    def register(self, application):
        self.handlers_registered = True

    def run_polling(self, **kwargs):
        self.poll_kwargs = kwargs


@pytest.fixture
def fresh_env(monkeypatch):
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST")
    monkeypatch.setattr(poll.firebase_client, "is_ready", lambda: True)
    return monkeypatch


def test_main_initializes_firebase_before_polling(monkeypatch, fresh_env):
    calls = []
    monkeypatch.setattr(
        poll.firebase_client, "init_firebase", lambda: calls.append("init")
    )
    app = FakeApplication()
    monkeypatch.setattr(poll, "bot", SimpleNamespace(register_handlers=app.register))
    monkeypatch.setattr(
        poll, "ApplicationBuilder", lambda: FakeApplicationBuilder(app)
    )

    poll.main()

    assert calls == ["init"]
    assert app.handlers_registered
    assert app.poll_kwargs["allowed_updates"] == ["message", "my_chat_member"]


def test_main_exits_when_firebase_unconfigured(monkeypatch, fresh_env):
    def _boom():
        raise FirebaseConfigError("no credentials configured")

    monkeypatch.setattr(poll.firebase_client, "init_firebase", _boom)

    with pytest.raises(SystemExit, match="no credentials configured"):
        poll.main()


def test_main_exits_without_token(monkeypatch):
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="TELEGRAM_BOT_TOKEN"):
        poll.main()
