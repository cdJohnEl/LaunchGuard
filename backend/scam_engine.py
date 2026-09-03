"""Two-tier scam engine: tier-1 regex blacklist, tier-2 LLM intent check."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

import regex as regex_lib

import llm_service

try:
    from contracts.schema import Decision, normalize_text
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from contracts.schema import Decision, normalize_text

DEFAULT_PATTERNS: list[str] = [
    r"send\s+(?:[\w.$%]+\s+){0,3}to\s+this\s+(?:address|wallet|contract)",
    r"(?:send|share|give|enter|provide|submit|paste)\s+(?:me\s+)?(?:your\s+)?(?:\w+\s+){0,2}"
    r"(?:seed|secret|recovery)\s*(?:phrase|words|keys?)",
    r"(?:seed|secret|recovery)\s*(?:phrase|words)\s+"
    r"(?:verif\w+|validat\w+|synchroni[sz]\w+|check|restore|migrat\w+)",
    r"(?:send|share|give|enter|paste|submit)\s+(?:me\s+)?(?:your\s+)?private\s*keys?",
    r"guaranteed\s+(?:\w+\s+){0,2}(?:profit|returns?|gains?|roi|income|yields?|payouts?)",
    r"double\s+your\s+(?:money|crypto|investment|btc|bitcoin|eth|ethereum|coins?|funds|usdt|usdc|sol|bnb|tokens?)",
    r"telegram[-\s]?premium\s+(?:giveaway|airdrop|gift|reward|bonus|bot)",
    r"telegr[a@4]m[a-z0-9@.\-_]{0,24}\."
    r"(?:xyz|top|click|link|shop|online|site|icu|ru|cc|info|biz|website|space)(?![a-z0-9])",
    r"(?:claim|collect|unlock|receive)\s+your\s+(?:\w+\s+){0,3}(?:airdrop|reward|bonus|gift|tokens?)",
    r"(?:get|claim|grab)\s+free\s+(?:crypto|bitcoin|btc|eth|ethereum|usdt|usdc|bnb|sol|tokens?|coins?)",
    # Both qualifiers required: % + cadence, or cadence + profit noun. Bare
    # "make monthly payments" / "earn daily interest" is ordinary English.
    r"\b(?:earn|make)\s+(?:\d+\s*%\s*(?:daily|weekly|monthly)"
    r"|(?:daily|weekly|monthly)\s+(?:profit|income|returns?|roi|gains?))\b",
    r"dm\s+me\s+(?:for|about)\s+(?:instant\s+)?(?:profit|profits|crypto|investment|returns?|signals?)",
    r"(?:verify|validate|synchroni[sz]e|sync|confirm|activate|unlock)\s+(?:your|the|my)\s+(?:crypto\s+)?wallet",
    r"verifikasi\s+(?:\w+\s+){0,3}wallet",
    r"connect\s+(?:your|the|my)\s+(?:crypto\s+)?wallet\s+(?:and\s+)?(?:to\s+)?"
    r"(?:claim|receive|unlock|collect|verify|activate)",
    r"(?:your|ur)\s+(?:wallet|account)\s+(?:has\s+been\s+|is\s+)?"
    r"(?:compromised|hacked|locked|suspended|frozen|desynchroni[sz]ed)",
    r"(?:first|last)\s+\d+\s+(?:users?|people|members?|holders?)\s+"
    r"(?:get|receive|will\s+get|win|claim)\s+(?:free\s+|a\s+free\s+)?"
    r"(?:tokens?|crypto|btc|bitcoin|eth|ethereum|usdt|usdc|bnb|sol|nfts?|airdrops?|whitelist|wl\b)",
]

_MAX_PATTERN_LENGTH = 500
_MAX_PATTERNS = 100
_MAX_CACHE_ENTRIES = 1000
# Founder-writable regexes are a ReDoS vector: each pattern gets a hard match
# timeout (the stdlib re module cannot be interrupted mid-search) and the whole
# scan gets a wall-clock budget, so one bad pattern can never stall the event loop.
_MATCH_TIMEOUT_SECONDS = 0.05
_TIER1_BUDGET_SECONDS = 0.25

_compiled_cache: dict[tuple[str, ...], tuple[tuple[object, str], ...]] = {}

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"(?:https?://|www\.|t\.me/)", re.IGNORECASE)
_WALLET_RE = re.compile(r"\bwallets?\b", re.IGNORECASE)
# PRD: a bare wallet address is a tier-2 trigger even without the word "wallet"
# ("send 0.1 ETH to 0xabc..." must reach the intent check).
_ETH_ADDRESS_TRIGGER_RE = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_BASE58_ADDRESS_TRIGGER_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{33,44}\b")

# Cyrillic/Greek/fullwidth lookalikes defeat literal pattern and trigger matching
# ("wаllet" with Cyrillic а). Folding lives in contracts.schema.normalize_text so
# the mock LLM provider folds the same way.

def _compiled(patterns: list[str]) -> tuple[tuple[object, str], ...]:
    # Patterns arrive from Firestore and cannot be trusted: non-strings dropped,
    # length-capped, count-capped, and compile-checked before ever touching a
    # message.
    if not isinstance(patterns, (list, tuple)):
        patterns = []
    key = tuple(p for p in patterns if isinstance(p, str))
    cached = _compiled_cache.get(key)
    if cached is not None:
        return cached
    compiled: list[tuple[object, str]] = []
    for raw in key[:_MAX_PATTERNS]:
        if not isinstance(raw, str) or len(raw) > _MAX_PATTERN_LENGTH:
            continue
        try:
            compiled.append((regex_lib.compile(raw, regex_lib.IGNORECASE), raw))
        except regex_lib.error:
            continue
    result = tuple(compiled)
    if key and not result:
        logger.warning(
            "all %d configured patterns are invalid; tier-1 falls back to nothing "
            "until the pattern list is fixed",
            len(key),
        )
    if len(_compiled_cache) >= _MAX_CACHE_ENTRIES:
        _compiled_cache.clear()
    _compiled_cache[key] = result
    return result


def tier_one_match(text: str, patterns: Optional[list[str]] = None) -> Decision:
    # Contract: empty, missing, or garbage per-chat config falls back to the
    # engine defaults; only a real list can override them.
    sources = patterns if isinstance(patterns, (list, tuple)) and patterns else DEFAULT_PATTERNS
    haystack = normalize_text(text)
    deadline = time.monotonic() + _TIER1_BUDGET_SECONDS
    for compiled, source in _compiled(sources):
        if time.monotonic() > deadline:
            logger.warning(
                "tier-1 scan budget exceeded (%d patterns); message allowed", len(sources)
            )
            break
        try:
            found = compiled.search(haystack, timeout=_MATCH_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("pattern exceeded match timeout and was skipped: %r", source)
            continue
        except Exception as exc:
            logger.warning("pattern match failed (%s); skipped: %r", exc, source)
            continue
        if found:
            return Decision(
                delete=True,
                tier=1,
                reason=f"tier-1 blacklist match: {source}",
                matched_pattern=source,
            )
    return Decision(delete=False, tier=None, reason="no tier-1 match")


def is_tier_two_trigger(text: str) -> bool:
    normalized = normalize_text(text)
    # Address shapes are case-sensitive (base58 excludes lowercase l); scan raw.
    return bool(
        _URL_RE.search(normalized)
        or _WALLET_RE.search(normalized)
        or _ETH_ADDRESS_TRIGGER_RE.search(text)
        or _BASE58_ADDRESS_TRIGGER_RE.search(text)
    )


async def evaluate(text: str, patterns: Optional[list[str]] = None) -> Decision:
    # Tier 1 is CPU-bound regex scanning; run it off the event loop so a scan
    # burning its budget in one chat cannot stall every other chat.
    tier_one = await asyncio.to_thread(tier_one_match, text, patterns)
    if tier_one.delete:
        return tier_one
    if not is_tier_two_trigger(text):
        return Decision(delete=False, tier=None, reason="no trigger, tier 2 skipped")
    try:
        verdict = await llm_service.check_intent(text)
    except Exception:  # contract: LLM failure must fail open, never propagate
        return Decision(delete=False, tier=None, reason="llm_unavailable")
    if verdict.get("is_scam"):
        return Decision(
            delete=True,
            tier=2,
            reason=str(verdict.get("reason", "")),
        )
    return Decision(delete=False, tier=2, reason=str(verdict.get("reason", "")))
