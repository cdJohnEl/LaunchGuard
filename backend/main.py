"""FastAPI webhook server hosting the LaunchGuard Telegram bot.

Boots with zero env vars set: every optional piece (Firebase, bot, webhook)
degrades to a health flag or a 503 path instead of preventing startup.
"""
from __future__ import annotations

import contextlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update

import bot
import config
import firebase_client

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
ALLOWED_UPDATES = ["message", "my_chat_member"]
MAX_BODY_BYTES = 1_000_000


def _load_config_safe() -> config.Config:
    try:
        return config.load_config()
    except config.ConfigError:
        logger.warning("backend config incomplete; running with bot and webhook disabled")
        return config.Config(telegram_bot_token="", webhook_url="", webhook_secret="")


async def _startup(app: FastAPI) -> None:
    settings = _load_config_safe()
    app.state.settings = settings

    firebase_ready = False
    try:
        firebase_client.init_firebase()
        firebase_ready = firebase_client.is_ready()
    except Exception:
        logger.critical("Firebase init failed; group tracking disabled", exc_info=True)
    app.state.firebase_ready = firebase_ready

    application = None
    app.state.application = None
    if settings.telegram_bot_token:
        try:
            application = bot.build_application(settings.telegram_bot_token)
            await application.initialize()
            await application.start()
            if settings.webhook_url:
                await application.bot.set_webhook(
                    url=f"{settings.webhook_url}{WEBHOOK_PATH}",
                    secret_token=settings.webhook_secret or None,
                    allowed_updates=ALLOWED_UPDATES,
                )
                logger.info(
                    "Telegram webhook registered at %s%s", settings.webhook_url, WEBHOOK_PATH
                )
            app.state.application = application
        except Exception:
            logger.critical("Telegram bot startup failed; /webhook will 503", exc_info=True)
            app.state.application = None
            if application is not None:
                with contextlib.suppress(Exception):
                    await application.stop()
                with contextlib.suppress(Exception):
                    await application.shutdown()


async def _shutdown(app: FastAPI) -> None:
    application = getattr(app.state, "application", None)
    if application is not None:
        try:
            await application.stop()
            await application.shutdown()
        except Exception:
            logger.exception("Telegram application shutdown failed")
    try:
        firebase_client.close()
    except Exception:
        logger.exception("firebase_client.close failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _startup(app)
    try:
        yield
    finally:
        await _shutdown(app)


app = FastAPI(title="LaunchGuard", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "LaunchGuard Backend",
        "status": "online",
        "health": "/healthz",
        "docs": "/docs",
    }


@app.post(WEBHOOK_PATH)
async def webhook(request: Request) -> JSONResponse:
    application = getattr(request.app.state, "application", None)
    if application is None:
        return JSONResponse(status_code=503, content={"error": "bot_not_configured"})
    secret = getattr(request.app.state, "settings", config.Config("", "", "")).webhook_secret
    if secret:
        provided = request.headers.get(SECRET_HEADER, "")
        # compare_digest raises on non-ASCII str; compare bytes so a malformed
        # header gets a 403, not a 500.
        if not hmac.compare_digest(provided.encode("utf-8", "replace"), secret.encode()):
            return JSONResponse(status_code=403, content={"error": "forbidden"})
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"error": "payload_too_large"})
    body_bytes = await request.body()
    if len(body_bytes) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"error": "payload_too_large"})
    try:
        body = json.loads(body_bytes)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})
    # WHY: de_json raises on non-dict input (e.g. JSON arrays) -> 400, not 500.
    try:
        update = Update.de_json(body, application.bot) if isinstance(body, dict) else None
    except Exception:
        update = None
    if update is None:
        return JSONResponse(status_code=400, content={"error": "invalid_update"})
    await application.update_queue.put(update)
    return JSONResponse(content={"ok": True})


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    settings = getattr(request.app.state, "settings", None)
    return {
        "status": "ok",
        "firebase": bool(getattr(request.app.state, "firebase_ready", False)),
        "bot": getattr(request.app.state, "application", None) is not None,
        "llm_provider": str(getattr(settings, "llm_provider", "mock")),
    }
