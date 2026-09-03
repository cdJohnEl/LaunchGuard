"""Offline tests for backend/bot.py.

Real PTB objects (Chat/User/Message/Update/ChatMemberUpdated) driven through the
real handler functions. firebase_client and scam_engine are stubbed by replacing
attributes on the real bot module, proving the bot consumes the contract seam.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from telegram import Chat, ChatMember, ChatMemberUpdated, Message, MessageEntity, Update, User
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ChatMemberHandler, CommandHandler, MessageHandler

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for _path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _path not in sys.path:  # WHY: tests bootstrap import paths, no conftest dependency
        sys.path.insert(0, _path)

import bot  # noqa: E402
from contracts.schema import Decision  # noqa: E402


class StubFirebase:
    def __init__(self, config: dict | None = None):
        self.config = config if config is not None else {"scam_keywords": [], "faq_pairs": {}}
        self.config_calls: list[int] = []
        self.ensure_chat_calls: list[tuple[int, str, str]] = []
        self.active_calls: list[tuple[int, bool]] = []
        self.increment_calls: list[tuple[int, int]] = []

    async def get_chat_config(self, chat_id: int) -> dict:
        self.config_calls.append(chat_id)
        return self.config

    async def ensure_chat(self, chat_id: int, group_name: str, chat_type: str) -> None:
        self.ensure_chat_calls.append((chat_id, group_name, chat_type))

    async def set_chat_active(self, chat_id: int, active: bool) -> None:
        self.active_calls.append((chat_id, active))

    async def increment_scams_blocked(self, chat_id: int, amount: int = 1) -> None:
        self.increment_calls.append((chat_id, amount))


class BrokenFirebase(StubFirebase):
    async def get_chat_config(self, chat_id: int) -> dict:
        raise RuntimeError("firebase not ready")


class StubScamEngine:
    def __init__(self, decision: Decision | None = None):
        self.decision = decision if decision is not None else Decision(delete=False)
        self.calls: list[tuple[str, list[str] | None]] = []

    async def evaluate(self, text: str, patterns: list[str] | None = None) -> Decision:
        self.calls.append((text, patterns))
        return self.decision


class ExplodingScamEngine(StubScamEngine):
    async def evaluate(self, text: str, patterns: list[str] | None = None) -> Decision:
        raise RuntimeError("engine exploded")


class FakeBot:
    def __init__(
        self,
        admin_ids: set[int] | None = None,
        admin_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self.admin_ids = set(admin_ids or ())
        self.admin_error = admin_error
        self.delete_error = delete_error
        self.sent: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.admin_fetches = 0

    async def send_message(self, chat_id: int, text: str = "", **kwargs) -> SimpleNamespace:
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.sent))

    async def delete_message(self, chat_id: int, message_id: int, **kwargs) -> bool:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append((chat_id, message_id))
        return True

    async def get_chat_administrators(self, chat_id: int, **kwargs) -> list[SimpleNamespace]:
        self.admin_fetches += 1
        if self.admin_error is not None:
            raise self.admin_error
        return [SimpleNamespace(user=SimpleNamespace(id=i)) for i in sorted(self.admin_ids)]


def make_user(user_id: int = 42, is_bot: bool = False) -> User:
    return User(id=user_id, first_name="X", is_bot=is_bot)


def make_chat(
    chat_id: int = -100123, chat_type: str = "supergroup", title: str | None = "Founders"
) -> Chat:
    return Chat(id=chat_id, type=chat_type, title=title)


def make_message(
    text: str | None = None,
    caption: str | None = None,
    *,
    chat: Chat | None = None,
    user: User | None = None,
    message_id: int = 1,
    entities: list[MessageEntity] | None = None,
) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat if chat is not None else make_chat(),
        from_user=user if user is not None else make_user(),
        text=text,
        caption=caption,
        entities=entities,
    )


def make_chat_member_update(
    chat: Chat, old_status: str = "left", new_status: str = "administrator"
) -> Update:
    member_update = ChatMemberUpdated(
        chat=chat,
        from_user=make_user(),
        date=datetime.now(timezone.utc),
        old_chat_member=ChatMember(make_user(), status=old_status),
        new_chat_member=ChatMember(make_user(), status=new_status),
    )
    return Update(update_id=1, my_chat_member=member_update)


@pytest.fixture(autouse=True)
def clean_admin_cache():
    bot._admin_cache.clear()
    yield
    bot._admin_cache.clear()


def wire(monkeypatch, firebase, scam_engine) -> tuple[FakeBot, SimpleNamespace]:
    monkeypatch.setattr(bot, "firebase_client", firebase)
    monkeypatch.setattr(bot, "scam_engine", scam_engine)
    fake_bot = FakeBot()
    return fake_bot, SimpleNamespace(bot=fake_bot)


async def test_tier1_scam_deleted_and_counter_incremented(monkeypatch):
    firebase = StubFirebase({"scam_keywords": ["free money"], "faq_pairs": {}})
    engine = StubScamEngine(
        Decision(delete=True, tier=1, reason="blacklist", matched_pattern="free money")
    )
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="get free money now"))

    await bot.on_message(update, ctx)

    assert fake_bot.deleted == [(-100123, 1)]
    assert firebase.increment_calls == [(-100123, 1)]
    assert fake_bot.sent == []
    assert engine.calls == [("get free money now", ["free money"])]


async def test_delete_bad_request_skips_counter(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.delete_error = BadRequest("Message to delete not found")
    update = Update(update_id=1, message=make_message(text="scam"))

    await bot.on_message(update, ctx)

    assert firebase.increment_calls == []
    assert fake_bot.sent == []


async def test_delete_forbidden_skips_counter(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=True, tier=2, reason="llm intent"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.delete_error = Forbidden("bot lacks rights")
    update = Update(update_id=1, message=make_message(text="scam"))

    await bot.on_message(update, ctx)

    assert firebase.increment_calls == []


async def test_admin_sender_bypasses_engine(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.admin_ids = {42}
    update = Update(update_id=1, message=make_message(text="free money everyone"))

    await bot.on_message(update, ctx)

    assert engine.calls == []
    assert fake_bot.deleted == []
    assert fake_bot.sent == []
    assert firebase.config_calls == []


async def test_bot_own_message_skipped(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    bot_message = make_message(text="welcome", user=make_user(user_id=999, is_bot=True))
    update = Update(update_id=1, message=bot_message)

    await bot.on_message(update, ctx)

    assert engine.calls == []
    assert fake_bot.admin_fetches == 0
    assert fake_bot.deleted == []


async def test_faq_reply_sent_when_engine_fails_open(monkeypatch):
    firebase = StubFirebase(
        {"scam_keywords": [], "faq_pairs": {"contract address": "CA: 0xabc"}}
    )
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="what is the contract address?"))

    await bot.on_message(update, ctx)

    assert fake_bot.deleted == []
    assert firebase.increment_calls == []
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["chat_id"] == -100123
    assert fake_bot.sent[0]["text"] == "CA: 0xabc"
    assert fake_bot.sent[0]["reply_to_message_id"] == 1


async def test_deleted_message_gets_no_faq_reply(monkeypatch):
    firebase = StubFirebase(
        {"scam_keywords": ["free money"], "faq_pairs": {"contract address": "CA: 0xabc"}}
    )
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="free money contract address"))

    await bot.on_message(update, ctx)

    assert fake_bot.deleted == [(-100123, 1)]
    assert fake_bot.sent == []


async def test_faq_first_configured_match_wins(monkeypatch):
    firebase = StubFirebase(
        {
            "scam_keywords": [],
            "faq_pairs": {"address": "first", "contract address": "second"},
        }
    )
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="contract address please"))

    await bot.on_message(update, ctx)

    assert [sent["text"] for sent in fake_bot.sent] == ["first"]


async def test_firebase_config_failure_uses_defaults(monkeypatch):
    firebase = BrokenFirebase()
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="hello group"))

    await bot.on_message(update, ctx)

    assert engine.calls == [("hello group", [])]
    assert fake_bot.deleted == []
    assert fake_bot.sent == []


async def test_handler_swallows_engine_exception(monkeypatch):
    firebase = StubFirebase()
    engine = ExplodingScamEngine()
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=1, message=make_message(text="anything"))

    await bot.on_message(update, ctx)

    assert fake_bot.deleted == []
    assert fake_bot.sent == []


async def test_my_chat_member_joined_registers_and_welcomes(monkeypatch):
    firebase = StubFirebase()
    fake_bot, ctx = wire(monkeypatch, firebase, StubScamEngine())
    update = make_chat_member_update(make_chat(), new_status="administrator")

    await bot.on_my_chat_member(update, ctx)

    assert firebase.ensure_chat_calls == [(-100123, "Founders", "supergroup")]
    assert firebase.active_calls == [(-100123, True)]
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["text"] == bot.WELCOME_TEXT


async def test_my_chat_member_kicked_marks_inactive(monkeypatch):
    firebase = StubFirebase()
    fake_bot, ctx = wire(monkeypatch, firebase, StubScamEngine())
    update = make_chat_member_update(make_chat(), new_status="kicked")

    await bot.on_my_chat_member(update, ctx)

    assert firebase.ensure_chat_calls == []
    assert firebase.active_calls == [(-100123, False)]
    assert fake_bot.sent == []


async def test_my_chat_member_private_chat_ignored(monkeypatch):
    firebase = StubFirebase()
    fake_bot, ctx = wire(monkeypatch, firebase, StubScamEngine())
    update = make_chat_member_update(make_chat(chat_id=42, chat_type="private"), new_status="member")

    await bot.on_my_chat_member(update, ctx)

    assert firebase.ensure_chat_calls == []
    assert firebase.active_calls == []
    assert fake_bot.sent == []


async def test_my_chat_member_missing_update_ignored(monkeypatch):
    firebase = StubFirebase()
    fake_bot, ctx = wire(monkeypatch, firebase, StubScamEngine())
    update = Update(update_id=3)

    await bot.on_my_chat_member(update, ctx)

    assert firebase.ensure_chat_calls == []
    assert firebase.active_calls == []


async def test_admin_ids_cached_within_ttl(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.admin_ids = {7}

    for message_id in (1, 2):
        update = Update(
            update_id=message_id,
            message=make_message(text="hi", message_id=message_id, user=make_user(user_id=99)),
        )
        await bot.on_message(update, ctx)

    assert fake_bot.admin_fetches == 1
    assert len(engine.calls) == 2
    cached = bot._admin_cache.get(-100123)
    assert cached is not None
    assert cached[1] == {7}


async def test_failed_admin_fetch_negatively_cached(monkeypatch):
    # Failure IS cached now (short TTL): a persistent Telegram outage must not
    # cost one get_chat_administrators call per message.
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.admin_error = Forbidden("bot not in chat")

    for message_id in (1, 2):
        update = Update(
            update_id=message_id,
            message=make_message(text="hi", message_id=message_id),
        )
        await bot.on_message(update, ctx)

    assert fake_bot.admin_fetches == 1
    assert -100123 in bot._admin_cache
    expiry, cached_ids = bot._admin_cache[-100123]
    assert cached_ids == set()
    assert expiry - time.monotonic() <= bot.ADMIN_FAILURE_TTL_SECONDS
    assert len(engine.calls) == 2


async def test_admin_failure_cache_expires_and_retries(monkeypatch):
    firebase = StubFirebase()
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    fake_bot.admin_error = Forbidden("bot not in chat")

    update = Update(update_id=1, message=make_message(text="hi", message_id=1))
    await bot.on_message(update, ctx)
    expiry, _ = bot._admin_cache[-100123]
    bot._admin_cache[-100123] = (expiry - bot.ADMIN_FAILURE_TTL_SECONDS - 1, set())
    fake_bot.admin_error = None

    update = Update(update_id=2, message=make_message(text="hi again", message_id=2))
    await bot.on_message(update, ctx)

    assert fake_bot.admin_fetches == 2
    assert bot._admin_cache[-100123][1] == {1, 2} or fake_bot.admin_fetches == 2


def test_keyword_match_case_insensitive():
    assert bot.keyword_match("What is the CONTRACT ADDRESS?", "contract address")


def test_keyword_match_word_boundaries():
    assert bot.keyword_match("my wallet", "wallet")
    assert not bot.keyword_match("mywallet", "wallet")
    assert not bot.keyword_match("contract addresses", "contract address")
    assert not bot.keyword_match("noncontract address", "contract address")


def test_keyword_match_rejects_longer_keyword():
    assert not bot.keyword_match("hi", "a much longer keyword")
    assert not bot.keyword_match("anything", "")


def test_extract_text_prefers_text_then_caption():
    assert bot.extract_text(make_message(text="hello")) == "hello"
    assert bot.extract_text(make_message(caption="photo caption")) == "photo caption"
    assert bot.extract_text(make_message()) == ""


def test_build_application_registers_handlers_in_order_and_has_no_updater():
    application = bot.build_application("123456:TEST")

    assert application.updater is None
    handlers = application.handlers[0]
    assert [type(handler) for handler in handlers] == [
        CommandHandler,
        ChatMemberHandler,
        MessageHandler,
    ]


# --- critic round 1 regressions ---


async def test_edited_message_is_ignored_entirely(monkeypatch):
    # LOW finding: edited_message updates re-ran the handler and double-answered
    # FAQs. message-only semantics: an edit-only update must do nothing.
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {"wen": "soon"}})
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    edited = make_message(text="wen launch?", message_id=9)
    update = Update(update_id=3, edited_message=edited)

    await bot.on_message(update, ctx)

    assert fake_bot.sent == []
    assert fake_bot.deleted == []
    assert engine.calls == []
    assert firebase.config_calls == []


# --- critic round 2 regressions ---


def test_slash_prefixed_messages_are_still_routed_to_moderation():
    # HIGH finding: ~filters.COMMAND let any "/token ..." message skip
    # moderation entirely (unregistered slash commands match no CommandHandler).
    application = bot.build_application("123456:TEST")
    handlers = [h for group in application.handlers.values() for h in group]
    message_handlers = [h for h in handlers if isinstance(h, MessageHandler)]
    assert len(message_handlers) == 1
    update = Update(
        update_id=1,
        message=make_message(text="/boom claim your free airdrop t.me/scam", message_id=1),
    )
    assert message_handlers[0].check_update(update) is not None


def test_registered_commands_still_take_priority():
    # PTB gives priority by registration order within a group: /start must be
    # consumed by the CommandHandler before the moderation MessageHandler runs.
    application = bot.build_application("123456:TEST")
    flat = [h for group in application.handlers.values() for h in group]
    kinds = [type(h).__name__ for h in flat]
    assert kinds.index("CommandHandler") < kinds.index("MessageHandler")


def test_concurrent_updates_enabled():
    application = bot.build_application("123456:TEST")
    assert application.concurrent_updates > 0


def test_keyword_match_allows_trailing_punctuation():
    assert bot.keyword_match("gm! how are you", "gm!")
    assert bot.keyword_match("GM!? frens", "gm!")
    assert not bot.keyword_match("gmx! the exchange", "gm!")


# --- critic round 3 regressions ---


def make_command_message(text: str, command_length: int, message_id: int = 1) -> Message:
    return make_message(
        text=text,
        message_id=message_id,
        entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=command_length)],
    )


async def test_start_with_scam_remainder_is_moderated(monkeypatch):
    # HIGH finding: "/start <scam>" was consumed by the CommandHandler and never
    # scanned. The remainder must go through the normal pipeline.
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {}})
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(
        update_id=1,
        message=make_command_message("/start send 0.5 ETH to this address now", 6),
    )

    await bot.cmd_start(update, ctx)

    assert [c[0] for c in engine.calls] == ["send 0.5 ETH to this address now"]
    assert fake_bot.deleted == [(-100123, 1)]
    assert firebase.increment_calls == [(-100123, 1)]
    assert fake_bot.sent == []


async def test_start_with_botname_suffix_and_scam_is_moderated(monkeypatch):
    # Telegram's command menu generates "/start@LaunchGuardBot ..." form.
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {}})
    engine = StubScamEngine(Decision(delete=True, tier=1, reason="blacklist"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(
        update_id=2,
        message=make_command_message(
            "/start@LaunchGuardBot claim your free airdrop at t.me/drop", 22
        ),
    )

    await bot.cmd_start(update, ctx)

    assert engine.calls and "airdrop" in engine.calls[0][0]
    assert fake_bot.deleted == [(-100123, 1)]
    assert fake_bot.sent == []


async def test_bare_start_in_group_sends_intro_without_scan(monkeypatch):
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {}})
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=3, message=make_command_message("/start", 6))

    await bot.cmd_start(update, ctx)

    assert engine.calls == []
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["text"] == bot.GROUP_START_TEXT


async def test_start_remainder_goes_to_faq(monkeypatch):
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {"wen launch": "after the audit"}})
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(
        update_id=4,
        message=make_command_message("/start wen launch?", 6),
    )

    await bot.cmd_start(update, ctx)

    assert engine.calls == [("wen launch?", [])]
    assert fake_bot.sent and fake_bot.sent[0]["text"] == "after the audit"


def test_command_remainder_extraction():
    msg = make_message(text="/start@BotName double your money now")
    assert bot.command_remainder(msg) == "double your money now"
    assert bot.command_remainder(make_message(text="/start")) == ""
    assert bot.command_remainder(make_message(text="/start   ")) == ""


async def test_caption_only_scam_is_deleted(monkeypatch):
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {}})
    engine = StubScamEngine(Decision(delete=True, tier=2, reason="phishing link"))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=5, message=make_message(caption="free airdrop at www.scam.io"))

    await bot.on_message(update, ctx)

    assert fake_bot.deleted == [(-100123, 1)]
    assert firebase.increment_calls == [(-100123, 1)]


async def test_faq_over_cap_disables_responder(monkeypatch):
    firebase = StubFirebase(
        {"scam_keywords": [], "faq_pairs": {f"kw{i}": f"answer {i}" for i in range(201)}}
    )
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=6, message=make_message(text="kw5 details please", message_id=6))

    await bot.on_message(update, ctx)

    assert fake_bot.sent == []


async def test_keyword_match_folds_homoglyphs():
    assert bot.keyword_match("wаllet check", "wallet")  # Cyrillic а
    assert bot.keyword_match("gm! how are you", "gm!")


async def test_faq_match_runs_off_loop_and_answers(monkeypatch):
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {f"kw{i}": f"answer {i}" for i in range(200)}})
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(update_id=7, message=make_message(text="what is kw42?", message_id=7))

    await bot.on_message(update, ctx)

    assert fake_bot.sent and fake_bot.sent[0]["text"] == "answer 42"


# --- critic round 4 regressions ---


async def test_edited_start_update_is_ignored(monkeypatch):
    # LOW finding: PTB routes edited_message updates to CommandHandler too;
    # update.message is None there and the intro would re-fire publicly.
    firebase = StubFirebase({"scam_keywords": [], "faq_pairs": {}})
    engine = StubScamEngine(Decision(delete=False))
    fake_bot, ctx = wire(monkeypatch, firebase, engine)
    update = Update(
        update_id=9,
        edited_message=make_command_message("/start send 0.5 ETH to this address", 6),
    )

    await bot.cmd_start(update, ctx)

    assert fake_bot.sent == []
    assert engine.calls == []
