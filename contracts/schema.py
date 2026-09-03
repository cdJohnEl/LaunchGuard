"""Shared data contract for LaunchGuard (backend + frontend).

Firestore layout
----------------
Collection: "groups"
Document ID: str(chat_id)  e.g. "-1001234567890"

See contracts/firestore.md for the authoritative field reference. Both the
Python backend and the Next.js dashboard read/write this shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TypedDict

GROUP_COLLECTION = "groups"

DEFAULT_SUBSCRIPTION_STATUS = "trial"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def doc_id(chat_id: int) -> str:
    return str(chat_id)


class ScamVerdict(TypedDict):
    """What an LLM intent check returns (tier 2)."""

    is_scam: bool
    reason: str
    confidence: float


@dataclass
class Decision:
    """Outcome of running one message through the scam engine."""

    delete: bool
    tier: Optional[int] = None  # 1 = blacklist match, 2 = LLM intent
    reason: str = ""
    matched_pattern: Optional[str] = None
