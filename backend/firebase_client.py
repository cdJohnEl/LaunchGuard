"""Firestore data layer for LaunchGuard group documents (contracts/firestore.md)."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import config

try:
    from contracts.schema import GROUP_COLLECTION, PUBLIC_COLLECTION, STATS_DOC, doc_id, now_iso
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from contracts.schema import GROUP_COLLECTION, PUBLIC_COLLECTION, STATS_DOC, doc_id, now_iso

CONFIG_TTL_SECONDS = 30.0


class FirebaseConfigError(Exception):
    """Firebase is not configured, not initialized, or failed to initialize."""


_db: Optional[Any] = None
_app: Optional[Any] = None
_config_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight_configs: dict[str, "asyncio.Future[dict[str, Any]]"] = {}
_MAX_CACHE_ENTRIES = 1000


def _require_db() -> Any:
    if _db is None:
        raise FirebaseConfigError(
            "Firebase is not initialized. Fix: call firebase_client.init_firebase() once at startup."
        )
    return _db


def init_firebase() -> None:
    global _db, _app
    if _db is not None:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as exc:
        raise FirebaseConfigError(
            "firebase-admin is not installed. "
            "Fix: cd backend && .venv/bin/pip install -r requirements.txt"
        ) from exc

    path = config.google_credentials_path()
    raw_json = config.google_credentials_json()
    cred_source = "credentials"
    try:
        if path:
            cred_source = "GOOGLE_APPLICATION_CREDENTIALS"
            cred = credentials.Certificate(path)
        elif raw_json:
            cred_source = "FIREBASE_SERVICE_ACCOUNT_JSON"
            try:
                cred = credentials.Certificate(json.loads(raw_json))
            except json.JSONDecodeError as exc:
                raise FirebaseConfigError(
                    "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON. "
                    "Fix: paste the full service-account JSON as one string, or set "
                    "GOOGLE_APPLICATION_CREDENTIALS to the file path instead. See backend/.env.example."
                ) from exc
        else:
            raise FirebaseConfigError(
                "No Firebase credentials configured. "
                "Fix: set GOOGLE_APPLICATION_CREDENTIALS to the path of a service-account JSON file, "
                "or set FIREBASE_SERVICE_ACCOUNT_JSON to the full JSON string. See backend/.env.example."
            )

        try:
            _app = firebase_admin.initialize_app(cred)
        except ValueError:
            _app = firebase_admin.get_app()
        _db = firestore.client(_app)
    except FirebaseConfigError:
        raise
    except Exception as exc:
        raise FirebaseConfigError(
            f"Firebase initialization failed: {exc}. "
            f"Fix: verify {cred_source} points to a valid service-account JSON with Firestore access."
        ) from exc


def is_ready() -> bool:
    return _db is not None


def close() -> None:
    global _db, _app
    _config_cache.clear()
    _inflight_configs.clear()
    if _app is not None:
        try:
            _app.delete()
        except Exception:
            pass  # app never finished initializing or was already deleted; close must not throw
    _app = None
    _db = None


async def ensure_chat(chat_id: int, group_name: str, chat_type: str) -> None:
    # chat_type is accepted per contracts/backend_api.md but not persisted: contracts/firestore.md
    # defines the document shape and has no chat_type field.
    db = _require_db()
    from google.api_core.exceptions import AlreadyExists
    from google.cloud.exceptions import NotFound

    def _write() -> None:
        ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))
        now = now_iso()
        try:
            # create() fails atomically when the doc exists, so a concurrent
            # increment/faq write can never be clobbered by default-seeding.
            ref.create(
                {
                    "chat_id": chat_id,
                    "group_name": group_name,
                    "owner_uid": None,
                    "active": True,
                    "subscription_status": "trial",
                    "scams_blocked": 0,
                    "scam_keywords": [],
                    "faq_pairs": {},
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except AlreadyExists:
            existing = ref.get().to_dict() or {}
            payload = {
                "chat_id": chat_id,
                "group_name": group_name,
                "active": True,
                "updated_at": now,
            }
            # Backfill fields a partial doc (created by a counter increment or
            # FAQ write before registration) is missing; never overwrite real values.
            for field, default in (
                ("created_at", now),
                ("owner_uid", None),
                ("subscription_status", "trial"),
                ("scam_keywords", []),
            ):
                if field not in existing:
                    payload[field] = default
            # faq_pairs must NEVER appear in a patch for an existing doc: set()
            # merges at top level only and would replace the whole map with {}.
            # update() patches fields, so a concurrent faq write survives.
            try:
                ref.update(payload)
            except NotFound:
                ref.create(
                    {
                        "chat_id": chat_id,
                        "group_name": group_name,
                        "owner_uid": None,
                        "active": True,
                        "subscription_status": "trial",
                        "scams_blocked": 0,
                        "scam_keywords": [],
                        "faq_pairs": {},
                        "created_at": now,
                        "updated_at": now,
                    }
                )

    await asyncio.to_thread(_write)
    _config_cache.pop(doc_id(chat_id), None)


def _transactional(db: Any):
    # Module-level seam so tests can swap the SDK's retrying wrapper for a
    # passthrough while exercising the claim logic against the fake.
    from google.cloud.firestore_v1 import transaction as firestore_transaction

    return firestore_transaction.transactional


async def claim_group(chat_id: int, owner_uid: str) -> str:
    """Bind owner_uid to an unowned group. Returns "claimed", "taken",
    or "not_found". Admin SDK path: proof-of-control is enforced by the bot
    (the /claim sender must be a Telegram group admin), never by the client."""
    db = _require_db()
    transactional = _transactional(db)

    def _claim() -> str:
        ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))

        @transactional
        def _tx(transaction) -> str:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return "not_found"
            current = (snap.to_dict() or {}).get("owner_uid")
            if isinstance(current, str) and current != "" and current != owner_uid:
                return "taken"
            transaction.update(ref, {"owner_uid": owner_uid, "updated_at": now_iso()})
            return "claimed"

        return _tx(db.transaction())

    result = await asyncio.to_thread(_claim)
    _config_cache.pop(doc_id(chat_id), None)
    return result


async def unclaim_group(chat_id: int) -> str:
    """Admin-SDK recovery: release a group's ownership (owner_uid -> null).
    Reached only through the bot's admin-gated /unclaim command. Returns
    "cleared" or "not_found"."""
    db = _require_db()
    transactional = _transactional(db)

    def _unclaim() -> str:
        ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))

        @transactional
        def _tx(transaction) -> str:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return "not_found"
            transaction.update(ref, {"owner_uid": None, "updated_at": now_iso()})
            return "cleared"

        return _tx(db.transaction())

    result = await asyncio.to_thread(_unclaim)
    _config_cache.pop(doc_id(chat_id), None)
    return result


async def set_chat_active(chat_id: int, active: bool) -> None:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))
    await asyncio.to_thread(
        lambda: ref.set({"active": active, "updated_at": now_iso()}, merge=True)
    )
    await refresh_active_groups_count()


def _count_active_docs(db: Any) -> int:
    query = db.collection(GROUP_COLLECTION).where("active", "==", True).count()
    return int(query.get()[0][0].value)


async def refresh_active_groups_count() -> None:
    # Joins/leaves are rare events: recompute instead of risking a drifted
    # increment-only counter (remove + re-add would double-count otherwise).
    db = _require_db()
    active = await asyncio.to_thread(_count_active_docs, db)
    await asyncio.to_thread(
        lambda: db.collection(PUBLIC_COLLECTION).document(STATS_DOC).set(
            {"active_groups": active, "updated_at": now_iso()}, merge=True
        )
    )


async def increment_scams_blocked(chat_id: int, amount: int = 1) -> None:
    db = _require_db()
    from firebase_admin import firestore

    def _write() -> None:
        # One atomic batch: the per-group counter and the public landing total
        # can never drift apart.
        batch = db.batch()
        batch.set(
            db.collection(GROUP_COLLECTION).document(doc_id(chat_id)),
            {"scams_blocked": firestore.Increment(amount), "updated_at": now_iso()},
            merge=True,
        )
        batch.set(
            db.collection(PUBLIC_COLLECTION).document(STATS_DOC),
            {"total_blocked": firestore.Increment(amount), "updated_at": now_iso()},
            merge=True,
        )
        batch.commit()

    await asyncio.to_thread(_write)


async def get_chat(chat_id: int) -> Optional[dict]:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))
    snap = await asyncio.to_thread(ref.get)
    if not snap.exists:
        return None
    return snap.to_dict()


async def get_chat_config(chat_id: int) -> dict:
    db = _require_db()
    key = doc_id(chat_id)
    cached = _config_cache.get(key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < CONFIG_TTL_SECONDS:
        return {"scam_keywords": list(cached[1]["scam_keywords"]), "faq_pairs": dict(cached[1]["faq_pairs"])}
    # Single-flight: a burst of messages in a cold chat shares one Firestore read
    # instead of stampeding the backend with N identical reads. shield() keeps one
    # cancelled waiter from killing the shared load for the rest; eviction happens
    # via done-callback so a cancelled waiter cannot orphan or evict the load.
    future = _inflight_configs.get(key)
    if future is None:
        future = asyncio.ensure_future(_load_config(key))

        def _evict(done: "asyncio.Future[dict[str, Any]]", key: str = key) -> None:
            if _inflight_configs.get(key) is done:
                _inflight_configs.pop(key, None)

        future.add_done_callback(_evict)
        _inflight_configs[key] = future
    try:
        entry = await asyncio.shield(future)
    except asyncio.CancelledError:
        raise
    return {"scam_keywords": list(entry["scam_keywords"]), "faq_pairs": dict(entry["faq_pairs"])}


async def _load_config(key: str) -> dict[str, Any]:
    data = await get_chat(int(key))
    entry = {
        "scam_keywords": list(data.get("scam_keywords") or []) if data else [],
        "faq_pairs": dict(data.get("faq_pairs") or {}) if data else {},
    }
    if len(_config_cache) >= _MAX_CACHE_ENTRIES:
        _config_cache.clear()
    _config_cache[key] = (time.monotonic(), entry)
    return entry


async def set_faq_pair(chat_id: int, keyword: str, response: str) -> None:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))
    # A whitespace-only keyword would phrase-match nearly every message.
    if not keyword.strip():
        return

    def _write() -> None:
        # Nested-dict set(merge=True) is the only correct form on this SDK:
        # set() does NOT expand dotted string keys (they become a literal
        # top-level field), and update() rejects FieldPath keys outright
        # (TypeError on mixed keys, AttributeError on .strip() otherwise).
        # With merge=True the SDK leaf-merges, mask = faq_pairs.`keyword`,
        # so sibling pairs survive and dot keywords stay one segment.
        ref.set(
            {
                "faq_pairs": {keyword: response},
                "updated_at": now_iso(),
            },
            merge=True,
        )

    await asyncio.to_thread(_write)
    _config_cache.pop(doc_id(chat_id), None)


async def delete_faq_pair(chat_id: int, keyword: str) -> None:
    db = _require_db()
    from firebase_admin import firestore

    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))

    def _delete() -> None:
        # merge-set with a DELETE_FIELD leaf; same wire semantics as above.
        if not ref.get().exists:
            return  # deleting a pair from a chat with no document is a no-op
        ref.set(
            {
                "faq_pairs": {keyword: firestore.DELETE_FIELD},
                "updated_at": now_iso(),
            },
            merge=True,
        )

    await asyncio.to_thread(_delete)
    _config_cache.pop(doc_id(chat_id), None)


async def list_all_groups() -> list[dict[str, Any]]:
    db = _require_db()

    def _read() -> list[dict[str, Any]]:
        docs = db.collection(GROUP_COLLECTION).stream()
        results: list[dict[str, Any]] = []
        for d in docs:
            data = d.to_dict() or {}
            data["id"] = d.id
            if "chat_id" not in data:
                try:
                    data["chat_id"] = int(d.id)
                except ValueError:
                    data["chat_id"] = d.id
            results.append(data)
        results.sort(
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True
        )
        return results

    return await asyncio.to_thread(_read)


async def get_admin_stats() -> dict[str, Any]:
    groups = await list_all_groups()
    total_groups = len(groups)
    active_groups = sum(1 for g in groups if g.get("active", False))
    claimed_groups = sum(1 for g in groups if bool(g.get("owner_uid")))
    total_blocked = sum(int(g.get("scams_blocked", 0) or 0) for g in groups)
    return {
        "total_groups": total_groups,
        "active_groups": active_groups,
        "claimed_groups": claimed_groups,
        "total_blocked": total_blocked,
    }


async def create_group_manual(
    chat_id: int,
    group_name: str,
    active: bool = True,
    owner_uid: Optional[str] = None,
    subscription_status: str = "trial",
) -> dict[str, Any]:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))
    now = now_iso()
    doc_data = {
        "chat_id": chat_id,
        "group_name": group_name,
        "owner_uid": owner_uid or None,
        "active": bool(active),
        "subscription_status": subscription_status,
        "scams_blocked": 0,
        "scam_keywords": [],
        "faq_pairs": {},
        "created_at": now,
        "updated_at": now,
    }

    def _create() -> dict[str, Any]:
        ref.set(doc_data, merge=True)
        return ref.get().to_dict() or doc_data

    created = await asyncio.to_thread(_create)
    _config_cache.pop(doc_id(chat_id), None)
    await refresh_active_groups_count()
    return created


async def update_group(chat_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))

    def _update() -> dict[str, Any]:
        payload = dict(updates)
        payload["updated_at"] = now_iso()
        ref.set(payload, merge=True)
        snap = ref.get()
        return snap.to_dict() or {}

    updated = await asyncio.to_thread(_update)
    _config_cache.pop(doc_id(chat_id), None)
    if "active" in updates:
        await refresh_active_groups_count()
    return updated


async def delete_group(chat_id: int) -> bool:
    db = _require_db()
    ref = db.collection(GROUP_COLLECTION).document(doc_id(chat_id))

    def _del() -> bool:
        ref.delete()
        return True

    res = await asyncio.to_thread(_del)
    _config_cache.pop(doc_id(chat_id), None)
    await refresh_active_groups_count()
    return res


def _clean_path(path: str) -> str:
    if not path or not isinstance(path, str) or not path.strip():
        return "/"
    p = path.strip().split("?")[0].split("#")[0]
    return p[:64] if p else "/"


def _clean_referrer(ref: str) -> str:
    if not ref or not isinstance(ref, str) or not ref.strip():
        return "Direct / Unknown"
    r = ref.lower().strip()
    if "t.co" in r or "twitter.com" in r or "x.com" in r:
        return "X / Twitter"
    if "t.me" in r or "telegram.org" in r:
        return "Telegram"
    if "google." in r:
        return "Google Search"
    if "reddit." in r:
        return "Reddit"
    if "linkedin." in r:
        return "LinkedIn"
    if "github." in r:
        return "GitHub"
    if "localhost" in r or "127.0.0.1" in r:
        return "Local Dev"
    try:
        from urllib.parse import urlparse

        domain = urlparse(ref).netloc
        if domain:
            return domain.lower()
    except Exception:
        pass
    return "Direct / Unknown"


async def record_pageview(
    path: str, referrer: str, visitor_id: str, device: str
) -> dict[str, Any]:
    db = _require_db()
    from datetime import datetime, timezone
    from firebase_admin import firestore

    now_dt = datetime.now(timezone.utc)
    today = now_dt.strftime("%Y-%m-%d")
    now = now_iso()

    clean_p = _clean_path(path)
    clean_r = _clean_referrer(referrer)
    dev = device if device in ("desktop", "mobile", "tablet") else "desktop"
    v_id = (visitor_id or "anon")[:32]

    overview_ref = db.collection("analytics").document("overview")
    today_ref = db.collection("analytics").document(today)
    recent_ref = db.collection("analytics").document("recent")

    def _write() -> None:
        batch = db.batch()

        # Update overview
        batch.set(
            overview_ref,
            {
                "total_pageviews": firestore.Increment(1),
                "by_path": {clean_p: firestore.Increment(1)},
                "by_referrer": {clean_r: firestore.Increment(1)},
                "by_device": {dev: firestore.Increment(1)},
                "visitors_seen": firestore.ArrayUnion([v_id]),
                "updated_at": now,
            },
            merge=True,
        )

        # Update today doc
        batch.set(
            today_ref,
            {
                "date": today,
                "pageviews": firestore.Increment(1),
                "by_path": {clean_p: firestore.Increment(1)},
                "by_referrer": {clean_r: firestore.Increment(1)},
                "by_device": {dev: firestore.Increment(1)},
                "visitors": firestore.ArrayUnion([v_id]),
                "updated_at": now,
            },
            merge=True,
        )

        batch.commit()

        # Update recent doc (capped at 40 events)
        r_snap = recent_ref.get()
        r_events = (r_snap.to_dict() or {}).get("events", []) if r_snap.exists else []
        new_event = {
            "path": clean_p,
            "referrer": clean_r,
            "device": dev,
            "timestamp": now,
        }
        capped_events = [new_event] + r_events[:39]
        recent_ref.set({"events": capped_events, "updated_at": now}, merge=True)

    await asyncio.to_thread(_write)
    return {"ok": True}


async def get_analytics_summary() -> dict[str, Any]:
    db = _require_db()
    from datetime import datetime, timezone, timedelta

    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")

    overview_ref = db.collection("analytics").document("overview")
    recent_ref = db.collection("analytics").document("recent")

    days = [(now_dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

    def _read() -> dict[str, Any]:
        o_snap = overview_ref.get()
        o_data = o_snap.to_dict() or {}

        r_snap = recent_ref.get()
        r_events = (r_snap.to_dict() or {}).get("events", []) if r_snap.exists else []

        total_views = int(o_data.get("total_pageviews", 0))
        unique_visitors = len(o_data.get("visitors_seen", [])) or total_views

        by_path = dict(o_data.get("by_path") or {})
        by_ref = dict(o_data.get("by_referrer") or {})
        by_dev = dict(o_data.get("by_device") or {})

        top_paths = sorted(by_path.items(), key=lambda x: x[1], reverse=True)[:10]
        top_refs = sorted(by_ref.items(), key=lambda x: x[1], reverse=True)[:10]

        daily_trend = []
        today_views = 0
        today_uniques = 0

        for d in days:
            d_snap = db.collection("analytics").document(d).get()
            if d_snap.exists:
                d_data = d_snap.to_dict() or {}
                views = int(d_data.get("pageviews", 0))
                uniques = len(d_data.get("visitors", [])) or views
                if d == today_str:
                    today_views = views
                    today_uniques = uniques
                daily_trend.append({"date": d, "pageviews": views, "uniques": uniques})
            else:
                daily_trend.append({"date": d, "pageviews": 0, "uniques": 0})

        return {
            "total_pageviews": total_views,
            "unique_visitors": unique_visitors,
            "today_pageviews": today_views,
            "today_uniques": today_uniques,
            "top_paths": [{"path": k, "count": v} for k, v in top_paths],
            "top_referrers": [{"referrer": k, "count": v} for k, v in top_refs],
            "device_breakdown": by_dev,
            "daily_trend": daily_trend,
            "recent_visits": r_events[:30],
        }

    return await asyncio.to_thread(_read)


