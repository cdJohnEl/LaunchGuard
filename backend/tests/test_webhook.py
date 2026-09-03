"""Offline tests for backend/main.py webhook and health endpoints.

Route coroutines are called directly with a stub Request, so no lifespan, no
network, and no env vars are needed. app.state is provided by the stub.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for _path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _path not in sys.path:  # WHY: tests bootstrap import paths, no conftest dependency
        sys.path.insert(0, _path)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from telegram import Bot, Update  # noqa: E402

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class StubRequest:
    def __init__(self, app: SimpleNamespace, body=None, json_error: Exception | None = None, headers: dict | None = None):
        self.app = app
        self._body = body
        self._json_error = json_error
        self.headers = headers or {}

    async def body(self) -> bytes:
        if self._json_error is not None:
            return b"{not json"
        if self._body is None:
            return b"null"
        return json.dumps(self._body).encode("utf-8")


class FakeQueue:
    def __init__(self):
        self.items: list[Update] = []

    async def put(self, item: Update) -> None:
        self.items.append(item)


def make_state(
    application: SimpleNamespace | None = None,
    settings: SimpleNamespace | None = None,
    firebase_ready: bool = False,
) -> SimpleNamespace:
    state = SimpleNamespace()
    if settings is None:
        settings = SimpleNamespace(llm_provider="mock", webhook_secret="")
    state.settings = settings
    state.firebase_ready = firebase_ready
    state.application = application
    return state


def make_request(state: SimpleNamespace, body=None, headers: dict | None = None) -> StubRequest:
    return StubRequest(app=SimpleNamespace(state=state), body=body, headers=headers)


def make_application() -> SimpleNamespace:
    return SimpleNamespace(bot=Bot(token="123456:TEST"), update_queue=FakeQueue())


def update_body() -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": -100123, "type": "supergroup", "title": "Founders"},
            "from": {"id": 42, "is_bot": False, "first_name": "X"},
            "text": "hello group",
        },
    }


async def test_webhook_503_when_bot_unconfigured():
    response = await main.webhook(make_request(make_state(application=None), body={}))

    assert response.status_code == 503
    assert json.loads(response.body) == {"error": "bot_not_configured"}


async def test_webhook_403_on_bad_secret():
    state = make_state(
        application=make_application(), settings=SimpleNamespace(llm_provider="mock", webhook_secret="expected")
    )
    request = make_request(state, body=update_body(), headers={SECRET_HEADER: "wrong"})

    response = await main.webhook(request)

    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "forbidden"}
    assert state.application.update_queue.items == []


async def test_webhook_403_on_missing_secret_header():
    state = make_state(
        application=make_application(), settings=SimpleNamespace(llm_provider="mock", webhook_secret="expected")
    )

    response = await main.webhook(make_request(state, body=update_body(), headers={}))

    assert response.status_code == 403


async def test_webhook_200_puts_update_in_queue():
    application = make_application()
    state = make_state(
        application=application, settings=SimpleNamespace(llm_provider="mock", webhook_secret="expected")
    )
    request = make_request(state, body=update_body(), headers={SECRET_HEADER: "expected"})

    response = await main.webhook(request)

    assert response.status_code == 200
    assert json.loads(response.body) == {"ok": True}
    assert len(application.update_queue.items) == 1
    queued = application.update_queue.items[0]
    assert isinstance(queued, Update)
    assert queued.message.text == "hello group"
    assert queued.message.chat_id == -100123


async def test_webhook_200_without_secret_when_unset():
    application = make_application()
    state = make_state(application=application)

    response = await main.webhook(make_request(state, body=update_body(), headers={}))

    assert response.status_code == 200
    assert len(application.update_queue.items) == 1


async def test_webhook_400_on_invalid_json():
    request = StubRequest(
        app=SimpleNamespace(state=make_state(application=make_application())),
        json_error=json.JSONDecodeError("Expecting value", "doc", 0),
        headers={},
    )

    response = await main.webhook(request)

    assert response.status_code == 400
    assert json.loads(response.body) == {"error": "invalid_json"}


async def test_webhook_400_on_null_body():
    application = make_application()
    state = make_state(application=application)

    response = await main.webhook(make_request(state, body=None, headers={}))

    assert response.status_code == 400
    assert json.loads(response.body) == {"error": "invalid_update"}
    assert application.update_queue.items == []


async def test_healthz_reports_state():
    request = make_request(
        make_state(
            application=make_application(),
            settings=SimpleNamespace(llm_provider="claude_cli"),
            firebase_ready=True,
        )
    )

    body = await main.healthz(request)

    assert body == {"status": "ok", "firebase": True, "bot": True, "llm_provider": "claude_cli"}


async def test_healthz_degraded_without_lifespan():
    request = StubRequest(app=SimpleNamespace(state=SimpleNamespace()))

    body = await main.healthz(request)

    assert body == {"status": "ok", "firebase": False, "bot": False, "llm_provider": "mock"}


def test_app_boots_with_zero_env_vars(monkeypatch):
    for name in ("TELEGRAM_BOT_TOKEN", "WEBHOOK_URL", "TELEGRAM_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    # WHY: freeze config's dotenv loader so a stray backend/.env cannot leak into this test
    monkeypatch.setattr(main.config, "_dotenv_loaded", True)

    def _boom() -> None:
        raise RuntimeError("no firebase credentials")

    monkeypatch.setattr(main.firebase_client, "init_firebase", _boom)
    monkeypatch.setattr(main.firebase_client, "is_ready", lambda: False)
    monkeypatch.setattr(main.firebase_client, "close", lambda: None)

    with TestClient(main.app) as client:
        health = client.get("/healthz").json()
        assert health["status"] == "ok"
        assert health["firebase"] is False
        assert health["bot"] is False

        response = client.post("/webhook", json={})
        assert response.status_code == 503
        assert response.json() == {"error": "bot_not_configured"}


# --- critic round 1 regressions ---


async def test_webhook_403_on_non_ascii_secret_header():
    state = make_state(
        application=make_application(), settings=SimpleNamespace(llm_provider="mock", webhook_secret="expected")
    )
    request = make_request(state, body=update_body(), headers={SECRET_HEADER: "wŕong-✓"})

    response = await main.webhook(request)

    assert response.status_code == 403
    assert state.application.update_queue.items == []


async def test_webhook_413_on_oversized_body():
    application = make_application()
    state = make_state(application=application)

    class GiantRequest(StubRequest):
        async def body(self) -> bytes:
            return b"x" * (main.MAX_BODY_BYTES + 1)

    response = await main.webhook(GiantRequest(app=SimpleNamespace(state=state), headers={}))

    assert response.status_code == 413
    assert application.update_queue.items == []
