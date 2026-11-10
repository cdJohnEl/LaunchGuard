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
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_admin_authorized(request: Request) -> bool:
    key = (
        request.headers.get("X-Admin-Key")
        or request.headers.get("x-admin-key")
        or request.query_params.get("admin_key")
        or request.query_params.get("key")
    )
    if not key:
        return False
    expected = config.admin_api_key()
    return hmac.compare_digest(key.encode("utf-8", "replace"), expected.encode("utf-8"))


def _admin_auth_error() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error": "unauthorized", "message": "Invalid or missing X-Admin-Key header."},
    )


@app.get("/api/admin/stats")
async def admin_stats(request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    stats = await firebase_client.get_admin_stats()
    return JSONResponse(content=stats)


@app.get("/api/admin/groups")
async def admin_list_groups(request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    groups = await firebase_client.list_all_groups()
    return JSONResponse(content={"groups": groups})


@app.post("/api/admin/groups")
async def admin_create_group(request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})
    raw_chat_id = body.get("chat_id")
    if raw_chat_id is None:
        return JSONResponse(status_code=400, content={"error": "chat_id is required"})
    try:
        chat_id = int(raw_chat_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "chat_id must be an integer"})
    group_name = str(body.get("group_name", "")).strip() or f"Group {chat_id}"
    active = bool(body.get("active", True))
    owner_uid = body.get("owner_uid")
    if owner_uid is not None:
        owner_uid = str(owner_uid).strip() or None
    subscription_status = str(body.get("subscription_status", "trial"))
    created = await firebase_client.create_group_manual(
        chat_id=chat_id,
        group_name=group_name,
        active=active,
        owner_uid=owner_uid,
        subscription_status=subscription_status,
    )
    return JSONResponse(status_code=201, content={"ok": True, "group": created})


@app.get("/api/admin/groups/{chat_id}")
async def admin_get_group(chat_id: int, request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    group = await firebase_client.get_chat(chat_id)
    if group is None:
        return JSONResponse(status_code=404, content={"error": "group_not_found"})
    return JSONResponse(content={"group": group})


@app.patch("/api/admin/groups/{chat_id}")
async def admin_update_group(chat_id: int, request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "body must be an object"})
    allowed_fields = {
        "group_name",
        "active",
        "owner_uid",
        "subscription_status",
        "scams_blocked",
        "scam_keywords",
        "faq_pairs",
    }
    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if not updates:
        return JSONResponse(status_code=400, content={"error": "no_valid_fields_to_update"})
    updated = await firebase_client.update_group(chat_id, updates)
    return JSONResponse(content={"ok": True, "group": updated})


@app.delete("/api/admin/groups/{chat_id}")
async def admin_delete_group(chat_id: int, request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    deleted = await firebase_client.delete_group(chat_id)
    return JSONResponse(content={"ok": deleted, "chat_id": chat_id})


@app.post("/api/analytics/collect")
async def collect_analytics(request: Request) -> JSONResponse:
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "body must be an object"})

    path = str(body.get("path", "/"))
    # Don't track admin console visits to prevent self-traffic skew
    if path.startswith("/admin"):
        return JSONResponse(content={"ok": True, "skipped": True})

    referrer = str(body.get("referrer", ""))
    visitor_id = str(body.get("visitor_id", "anon"))
    device = str(body.get("device", "desktop"))

    await firebase_client.record_pageview(
        path=path,
        referrer=referrer,
        visitor_id=visitor_id,
        device=device,
    )
    return JSONResponse(content={"ok": True})


@app.get("/api/admin/analytics")
async def admin_analytics(request: Request) -> JSONResponse:
    if not _is_admin_authorized(request):
        return _admin_auth_error()
    if not getattr(request.app.state, "firebase_ready", False):
        return JSONResponse(status_code=503, content={"error": "firebase_not_ready"})
    summary = await firebase_client.get_analytics_summary()
    return JSONResponse(content=summary)




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
