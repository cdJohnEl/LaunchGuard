"""One-off (idempotent) backfill: seed public/stats from the existing groups.

Usage (from backend/): .venv/bin/python scripts/seed_public_stats.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import firebase_client  # noqa: E402
from contracts.schema import GROUP_COLLECTION, PUBLIC_COLLECTION, STATS_DOC  # noqa: E402


def main() -> None:
    firebase_client.init_firebase()
    db = firebase_client._db

    total_blocked = 0
    active_groups = 0
    groups = 0
    for doc in db.collection(GROUP_COLLECTION).stream():
        data = doc.to_dict() or {}
        groups += 1
        raw = data.get("scams_blocked")
        if isinstance(raw, (int, float)):
            total_blocked += max(0, int(raw))
        if data.get("active") is True:
            active_groups += 1

    db.collection(PUBLIC_COLLECTION).document(STATS_DOC).set(
        {
            "total_blocked": total_blocked,
            "active_groups": active_groups,
            "updated_at": firebase_client.now_iso(),
        },
        merge=True,
    )
    print(f"groups scanned: {groups}")
    print(f"public/stats -> total_blocked: {total_blocked}, active_groups: {active_groups}")


if __name__ == "__main__":
    main()
