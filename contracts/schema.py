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
import unicodedata

GROUP_COLLECTION = "groups"

# Cyrillic/Greek lookalike folding used by every matcher ("wаllet" with a
# Cyrillic а must not evade literal detection). NFKC handles fullwidth forms.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
        "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "і": "i", "ѕ": "s",
        "ј": "j", "һ": "h", "ԁ": "d", "ɡ": "g", "ο": "o", "α": "a", "ε": "e",
        "ρ": "p", "ν": "v", "κ": "k", "τ": "t", "ι": "i", "ς": "s", "υ": "u",
    }
)


def normalize_text(text: str) -> str:
    # lower() after NFKC and before the table: uppercase Cyrillic/Greek
    # homoglyphs (Рrofit, MОNEY) lowercase into the entries below. All
    # consumers match case-insensitively, so folding case is safe.
    return unicodedata.normalize("NFKC", text).lower().translate(_CONFUSABLES)

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
