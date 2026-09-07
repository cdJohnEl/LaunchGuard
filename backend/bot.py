"""Telegram handlers for LaunchGuard: scam deletion, FAQ auto-responder, group tracking.

Consumes the contracts/backend_api.md seam. firebase_client and scam_engine are
imported as modules (not from-imports) so tests can replace `bot.firebase_client`
and `bot.scam_engine` wholesale.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from telegram import Bot, ChatMember, Message, Update
from telegram.constants import ChatType
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import firebase_client
import scam_engine

try:
    from contracts.schema import Decision, normalize_text
except ImportError:  # WHY: repo root not on sys.path when launched from backend/
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from contracts.schema import Decision, normalize_text

logger = logging.getLogger(__name__)

ADMIN_CACHE_TTL_SECONDS = 300.0
ADMIN_FAILURE_TTL_SECONDS = 60.0
MAX_FAQ_PAIRS = 200
_MAX_ADMIN_CACHE_ENTRIES = 1000

_JOINED_STATUSES = frozenset(
    {ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.RESTRICTED, ChatMember.OWNER}
)
# PTB calls Telegram's "kicked" status BANNED.
_LEFT_STATUSES = frozenset({ChatMember.LEFT, ChatMember.BANNED})
_GROUP_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})

PRIVATE_START_TEXT = (
    "Hi! I'm LaunchGuard, the anti-scam guard for your Web3 community.\n\n"
    "Add me to your group, promote me to admin, and give me the "
    "'Delete messages' permission. Then I will:\n"
    "1. Delete scam messages (keyword blacklist + AI intent check)\n"
    "2. Auto-answer your configured FAQ keywords (e.g. 'contract address')\n\n"
    "Configure your scam keywords and FAQ answers in the LaunchGuard dashboard."
)
GROUP_START_TEXT = (
    "LaunchGuard is guarding this group.\n\n"
    "I delete scam messages and auto-answer configured FAQ keywords.\n"
    "Founder: promote me to admin with the 'Delete messages' permission, "
    "then set your scam keywords and FAQ answers in the LaunchGuard dashboard."
)


def welcome_text(chat_id: int) -> str:
    # The chat id is the one thing onboarding needs and the hardest to find:
    # post it in the welcome message so step 3 is a copy-paste.
    return (
        "Thanks for adding LaunchGuard! Promote me to admin with the "
        "'Delete messages' permission so I can remove scams.\n\n"
        f"This group's chat id: {chat_id}\n"
        "Paste it into the Launch Guard dashboard to connect the group and "
        "configure FAQ answers."
    )

_admin_cache: dict[int, tuple[float, set[int]]] = {}


CLAIM_USAGE_TEXT = (
    "Claim usage: type /claim followed by your founder code from the "
    "Launch Guard dashboard, e.g. /claim 8f2a1c..."
)

CLAIM_NOT_ADMIN_TEXT = "Only group admins can claim this group for a founder account."


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("claim", cmd_claim))
    application.add_handler(CommandHandler("unclaim", cmd_unclaim))
    application.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    # No ~filters.COMMAND here: registered commands are consumed by the
    # CommandHandler above, but a scam message starting with an unregistered
    # "/token" (clients auto-tag bot_command entities) must still be scanned.
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS,
            on_message,
        )
    )


def build_application(token: str) -> Application:
    application = ApplicationBuilder().token(token).updater(None).concurrent_updates(True).build()
    register_handlers(application)
    return application


def is_admin(sender_id: int, admin_ids: set[int]) -> bool:
    return sender_id in admin_ids


def keyword_match(text: str, keyword: str) -> bool:
    if not keyword or len(keyword) > len(text):
        return False
    return phrase_in_text(normalize_text(keyword), normalize_text(text))


def phrase_in_text(needle: str, haystack_normalized: str) -> bool:
    # Lookarounds instead of \b so keywords ending in punctuation ("gm!") can
    # match at all (no word char after "!"). Callers normalize once and reuse.
    if not needle or len(needle) > len(haystack_normalized):
        return False
    return (
        re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack_normalized, flags=re.IGNORECASE)
        is not None
    )


def extract_text(message: Message) -> str:
    return message.text or message.caption or ""


async def get_admin_ids(bot: Bot, chat_id: int) -> set[int]:
    now = time.monotonic()
    cached = _admin_cache.get(chat_id)
    if cached is not None and cached[0] > now:
        return cached[1]
    try:
        administrators = await bot.get_chat_administrators(chat_id)
    except TelegramError:
        # Negative-cache the failure too, or a persistent outage means one
        # Telegram API call for every single message in the chat.
        logger.warning("admin fetch failed for chat %s; treating as empty", chat_id)
        _admin_cache[chat_id] = (now + ADMIN_FAILURE_TTL_SECONDS, set())
        return set()
    admin_ids = {admin.user.id for admin in administrators if admin.user is not None}
    if len(_admin_cache) >= _MAX_ADMIN_CACHE_ENTRIES:
        _admin_cache.clear()
    _admin_cache[chat_id] = (now + ADMIN_CACHE_TTL_SECONDS, admin_ids)
    return admin_ids


def command_remainder(message: Message) -> str:
    # "/start@Bot double your money" -> "double your money"; bare "/start" -> "".
    text = message.text or ""
    parts = text.split(None, 1)
    if parts and parts[0].startswith("/"):
        return parts[1].strip() if len(parts) > 1 else ""
    return text.strip()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat = update.effective_chat
        message = update.message
        # message-only semantics: PTB routes edited_message updates to
        # CommandHandler too; update.message is None there and the remainder
        # would skip moderation while the intro re-fires publicly.
        if chat is None or message is None:
            return
        # A "/start <scam text>" must not be a moderation bypass: the
        # CommandHandler consumes the whole update, so anything after the
        # command token goes through the normal pipeline in groups.
        if chat.type in _GROUP_TYPES and command_remainder(message):
            sender = message.from_user
            if sender is not None and not sender.is_bot:
                await _moderate_and_answer(context, message, command_remainder(message))
                return
        text = PRIVATE_START_TEXT if chat.type == ChatType.PRIVATE else GROUP_START_TEXT
        await context.bot.send_message(chat_id=chat.id, text=text)
    except Exception:
        logger.exception("cmd_start failed for update %s", getattr(update, "update_id", None))


async def cmd_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat = update.effective_chat
        message = update.message
        if chat is None or message is None or chat.type not in _GROUP_TYPES:
            return
        founder_uid = command_remainder(message).split(None, 1)
        code = founder_uid[0] if founder_uid else ""
        if not code:
            await context.bot.send_message(chat_id=chat.id, text=CLAIM_USAGE_TEXT)
            return
        sender = message.from_user
        if sender is None or sender.is_bot:
            return
        if not is_admin(sender.id, await get_admin_ids(context.bot, chat.id)):
            await context.bot.send_message(chat_id=chat.id, text=CLAIM_NOT_ADMIN_TEXT)
            return
        result = await firebase_client.claim_group(chat.id, code)
        if result == "claimed":
            reply = "Claimed. This group's dashboard is bound to that founder account."
        elif result == "taken":
            reply = "This group is already claimed by another founder account."
        else:
            reply = (
                "This group isn't registered yet — remove and re-add me, "
                "then run /claim again."
            )
        await context.bot.send_message(chat_id=chat.id, text=reply)
    except Exception:
        logger.exception("cmd_claim failed for update %s", getattr(update, "update_id", None))


async def cmd_unclaim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat = update.effective_chat
        message = update.message
        if chat is None or message is None or chat.type not in _GROUP_TYPES:
            return
        sender = message.from_user
        if sender is None or sender.is_bot:
            return
        if not is_admin(sender.id, await get_admin_ids(context.bot, chat.id)):
            await context.bot.send_message(chat_id=chat.id, text=CLAIM_NOT_ADMIN_TEXT)
            return
        result = await firebase_client.unclaim_group(chat.id)
        if result == "cleared":
            reply = "Ownership released. Any admin can now /claim the group again."
        else:
            reply = "This group isn't registered — nothing to release."
        await context.bot.send_message(chat_id=chat.id, text=reply)
    except Exception:
        logger.exception("cmd_unclaim failed for update %s", getattr(update, "update_id", None))


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        member_update = update.my_chat_member
        if member_update is None:
            return
        chat = member_update.chat
        if chat is None or chat.type not in _GROUP_TYPES:
            return
        status = member_update.new_chat_member.status if member_update.new_chat_member else None
        if status in _JOINED_STATUSES:
            try:
                await firebase_client.ensure_chat(chat.id, chat.title or "", chat.type)
                await firebase_client.set_chat_active(chat.id, True)
            except Exception:
                logger.exception("failed to register chat %s in Firestore", chat.id)
            try:
                await context.bot.send_message(chat_id=chat.id, text=welcome_text(chat.id))
            except TelegramError:
                logger.warning("welcome message failed in chat %s", chat.id)
        elif status in _LEFT_STATUSES:
            try:
                await firebase_client.set_chat_active(chat.id, False)
            except Exception:
                logger.exception("failed to mark chat %s inactive", chat.id)
    except Exception:
        logger.exception("on_my_chat_member failed for update %s", getattr(update, "update_id", None))


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await _handle_message(update, context)
    except Exception:
        logger.exception("on_message failed for update %s", getattr(update, "update_id", None))


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # message-only semantics: edited_message updates re-run this handler and would
    # double-reply FAQs (and re-scan spam), so they are ignored entirely.
    message = update.message
    if message is None:
        return
    text = extract_text(message)
    sender = message.from_user
    if not text or sender is None or sender.is_bot:
        return
    await _moderate_and_answer(context, message, text)


async def _moderate_and_answer(
    context: ContextTypes.DEFAULT_TYPE, message: Message, text: str
) -> None:
    chat_id = message.chat_id
    sender = message.from_user
    if sender is None:
        return
    if is_admin(sender.id, await get_admin_ids(context.bot, chat_id)):
        return
    config = await _get_config(chat_id)
    decision = await scam_engine.evaluate(text, config["scam_keywords"])
    if decision.delete:
        await _delete_scam(context, message, sender.id, decision)
        return
    await _answer_faq(context, message, text, config["faq_pairs"])


async def _get_config(chat_id: int) -> dict:
    try:
        return await firebase_client.get_chat_config(chat_id)
    except Exception:
        logger.exception("get_chat_config failed for chat %s; using defaults", chat_id)
        return {"scam_keywords": [], "faq_pairs": {}}


async def _delete_scam(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    sender_id: int,
    decision: Decision,
) -> None:
    chat_id = message.chat_id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
    except (BadRequest, Forbidden):
        logger.info(
            "delete skipped in chat %s (message gone or missing rights); tier=%s reason=%s",
            chat_id,
            decision.tier,
            decision.reason,
        )
        return
    logger.info(
        "scam_deleted chat_id=%s user_id=%s tier=%s reason=%s",
        chat_id,
        sender_id,
        decision.tier,
        decision.reason,
    )
    try:
        await firebase_client.increment_scams_blocked(chat_id)
    except Exception:
        logger.exception("increment_scams_blocked failed for chat %s", chat_id)


async def _answer_faq(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    text: str,
    faq_pairs: dict[str, str],
) -> None:
    if not faq_pairs:
        return
    if len(faq_pairs) > MAX_FAQ_PAIRS:
        logger.warning(
            "chat %s has %d FAQ pairs (max %d); auto-responder disabled",
            message.chat_id,
            len(faq_pairs),
            MAX_FAQ_PAIRS,
        )
        return
    # Keyword matching is O(pairs) CPU work; a founder-configurable map must not
    # run on the event loop (20k pairs = seconds of loop stall per message).
    response = await asyncio.to_thread(_match_faq, text, faq_pairs)
    if response is None:
        return
    try:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response,
            reply_to_message_id=message.message_id,
        )
    except TelegramError:
        logger.warning("faq reply failed in chat %s", message.chat_id)


def _match_faq(text: str, faq_pairs: dict[str, str]) -> str | None:
    # The message is normalized once, not once per pair: 200 pairs x long
    # keywords previously re-folded the full text hundreds of times.
    normalized_text = normalize_text(text)
    for keyword, response in faq_pairs.items():
        if phrase_in_text(normalize_text(keyword), normalized_text):
            return response
    return None
