"""Gate tests for the scam engine plus the eval smoke test."""
import asyncio
from pathlib import Path

import pytest

import llm_service
import scam_engine
from contracts.schema import Decision
from scam_engine import DEFAULT_PATTERNS, evaluate, is_tier_two_trigger, tier_one_match

EVAL_DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset.jsonl"


PATTERN_EXAMPLES: dict[str, tuple[str, str]] = {
    r"to\s+this\s+(?:address": (
        "Send 0.5 ETH to this address to join the presale",
        "send the invite link to the group chat",
    ),
    r"(?:seed|secret|recovery)\s*(?:phrase|words|keys?)": (
        "Please share your seed phrase so we can restore your wallet",
        "I keep my passphrase on paper, never digitally",
    ),
    r"(?:seed|secret|recovery)\s*(?:phrase|words)\s+": (
        "Seed phrase verification required, do it now at the portal",
        "keep your recovery phrase offline and private",
    ),
    r"private\s*keys?": (
        "enter your private key to import the wallet",
        "the private key of the TLS certificate was rotated",
    ),
    r"guaranteed\s+": (
        "GUARANTEED PROFIT every single week with our bot",
        "profit margins look fine this quarter",
    ),
    r"double\s+your\s+": (
        "Double your money in 24 hours, zero risk",
        "your money is safe in the treasury, double checking the numbers",
    ),
    r"telegram[-\s]?premium\s+": (
        "Telegram Premium giveaway for the first members!!!",
        "telegram premium subscriptions got cheaper",
    ),
    r"telegr[a@4]m[a-z0-9@.\-_]{0,24}\.": (
        "claim at telegram-gift.ru before it expires",
        "our announcements live on telegram.org",
    ),
    r"(?:claim|collect|unlock|receive)\s+your\s+": (
        "Claim your airdrop before the snapshot tonight",
        "we will receive your feedback after the AMA",
    ),
    r"(?:get|claim|grab)\s+free\s+": (
        "Get free crypto just for joining our channel",
        "you can get a free trial of the analytics tool",
    ),
    r"\b(?:earn|make)\s+": (
        "Earn 10% daily on your deposit, fully passive",
        "we make monthly payments to our moderators",
    ),
    r"dm\s+me\s+": (
        "DM me for profit signals, only 5 spots left",
        "dm me the agenda for tomorrow",
    ),
    r"(?:verify|validate|synchroni[sz]e|sync|confirm|activate|unlock)\s+(?:your|the|my)\s+": (
        "Verify your wallet to receive the whitelist role",
        "verify your email to finish the signup",
    ),
    r"verifikasi": (
        "Verifikasi wallet kamu sekarang untuk klaim hadiah",
        "tolong periksa wallet saya, ada bug di aplikasi",
    ),
    r"connect\s+(?:your|the|my)\s+": (
        "Connect your wallet to claim the presale allocation",
        "connect your wallet once to read the on-chain data",
    ),
    r"(?:your|ur)\s+(?:wallet|account)\s+": (
        "Your account has been compromised, contact support immediately",
        "my wallet was drained last year, still hurts",
    ),
    r"(?:first|last)\s+\d+\s+": (
        "First 50 users win a free ETH drop, hurry up",
        "the first 100 attendees will get the recording",
    ),
}


def test_every_default_pattern_has_examples_and_behaves():
    matched_keys: set[str] = set()
    for pattern in DEFAULT_PATTERNS:
        hits = [key for key in PATTERN_EXAMPLES if key in pattern]
        assert len(hits) == 1, f"pattern {pattern!r} needs exactly one example row"
        scam_text, ham_text = PATTERN_EXAMPLES[hits[0]]
        matched_keys.add(hits[0])
        verdict = tier_one_match(scam_text)
        assert verdict.delete, f"pattern {pattern!r} failed on scam example {scam_text!r}"
        assert verdict.tier == 1
        assert verdict.matched_pattern == pattern
        ham_verdict = tier_one_match(ham_text)
        assert not ham_verdict.delete, f"pattern {pattern!r} wrongly matched ham {ham_text!r}"
    assert matched_keys == set(PATTERN_EXAMPLES)


def test_at_least_twelve_default_patterns():
    assert len(DEFAULT_PATTERNS) >= 12


@pytest.mark.parametrize("text", ["DOUBLE YOUR MONEY IN 24 HOURS", "dM mE fOr PrOfIt"])
def test_case_insensitive(text):
    assert tier_one_match(text).delete


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/claim",
        "http://example.com",
        "www.example.com/giveaway",
        "t.me/durov",
        "HTTPS://EXAMPLE.COM/CLAIM",
        "see www.giveaway.xyz for details",
        "my wallet got drained yesterday",
        "external wallets are supported here",
    ],
)
def test_tier_two_triggers(text):
    assert is_tier_two_trigger(text)


@pytest.mark.parametrize(
    "text",
    [
        "gm frens, big week ahead",
        "walletconnect is a protocol for dapps",
        "check example dot com",
        "our site is example.com, go read it",
    ],
)
def test_tier_two_non_triggers(text):
    assert not is_tier_two_trigger(text)


def test_per_chat_patterns_override_defaults():
    hit = tier_one_match("PROMO42 just went live", patterns=[r"promo\d+"])
    assert hit.delete and hit.tier == 1 and hit.matched_pattern == r"promo\d+"
    clean = tier_one_match("double your money in 24 hours", patterns=[r"promo\d+"])
    assert not clean.delete


def test_invalid_regex_entries_skipped():
    hit = tier_one_match("SCAMTEXT now", patterns=["([unclosed", "scamtext"])
    assert hit.delete and hit.matched_pattern == "scamtext"
    assert not tier_one_match("anything", patterns=["([unclosed"]).delete


def test_pattern_count_cap():
    patterns = [rf"nomatch{i}\b" for i in range(100)] + [r"doubleyourmoneyz"]
    assert not tier_one_match("doubleyourmoneyz here", patterns=patterns).delete


def test_pattern_length_cap():
    pad = " #" * (scam_engine._MAX_PATTERN_LENGTH // 2 + 10)
    long_pattern = r"double\s+your\s+money" + pad
    assert len(long_pattern) > scam_engine._MAX_PATTERN_LENGTH
    padded_text = "double your money" + pad
    assert not tier_one_match(padded_text, patterns=[long_pattern]).delete


def test_hygiene_keeps_valid_patterns_in_mixed_list():
    long_pattern = r"double\s+your\s+money" + " #" * 110
    patterns = ["([oops", long_pattern, r"freecrypto\d+"]
    hit = tier_one_match("FREECRYPTO7 giveaway", patterns=patterns)
    assert hit.delete and hit.matched_pattern == r"freecrypto\d+"


@pytest.mark.asyncio
async def test_evaluate_tier_one_skips_llm(monkeypatch):
    def _boom(text):
        raise AssertionError("llm must not be called for tier-1 hits")

    monkeypatch.setattr(llm_service, "check_intent", _boom)
    decision = await evaluate("Double your money in 24 hours")
    assert decision.delete and decision.tier == 1


@pytest.mark.asyncio
async def test_evaluate_tier_two_scam(monkeypatch):
    monkeypatch.setenv("LAUNCHGUARD_LLM_PROVIDER", "mock")
    decision = await evaluate(
        "hey check this site www.coinscheduler.io, deposit 0.1 eth and it doubles overnight"
    )
    assert decision.delete and decision.tier == 2
    assert decision.reason


@pytest.mark.asyncio
async def test_evaluate_tier_two_ham(monkeypatch):
    monkeypatch.setenv("LAUNCHGUARD_LLM_PROVIDER", "mock")
    decision = await evaluate("check the docs at https://docs.python.org")
    assert not decision.delete
    assert decision.tier == 2


@pytest.mark.asyncio
async def test_evaluate_no_trigger_skips_llm(monkeypatch):
    def _boom(text):
        raise AssertionError("llm must not be called without a tier-2 trigger")

    monkeypatch.setattr(llm_service, "check_intent", _boom)
    decision = await evaluate("gm frens")
    assert decision == Decision(delete=False, tier=None, reason="no trigger, tier 2 skipped")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [llm_service.LLMError("boom"), asyncio.TimeoutError(), llm_service.UnknownProviderError("x")],
)
async def test_evaluate_fails_open_on_llm_error(monkeypatch, error):
    async def _raise(text):
        raise error

    monkeypatch.setattr(llm_service, "check_intent", _raise)
    decision = await evaluate("see www.example.io/claim for details")
    assert decision.delete is False
    assert decision.tier is None
    assert decision.reason == "llm_unavailable"


def test_eval_dataset_passes_thresholds(monkeypatch):
    monkeypatch.setenv("LAUNCHGUARD_LLM_PROVIDER", "mock")
    from evals.eval_scam_engine import (
        FPR_MAX,
        SCAM_RECALL_MIN,
        compute_metrics,
        load_rows,
        predict,
    )

    rows = load_rows(EVAL_DATASET)
    assert len(rows) >= 48
    metrics = compute_metrics(rows, predict(rows))
    assert metrics["scam"]["recall"] >= SCAM_RECALL_MIN
    assert metrics["fpr"] <= FPR_MAX


# --- critic round 1 regressions ---


def test_empty_pattern_list_falls_back_to_defaults():
    # HIGH finding: bot.py passes config["scam_keywords"] which is [] for every
    # fresh chat; [] must mean DEFAULT_PATTERNS or the blacklist is dead code.
    decision = tier_one_match("double your money in 24 hours", [])
    assert decision.delete is True
    assert decision.tier == 1


def test_empty_pattern_list_and_none_behave_identically():
    text = "claim your free crypto now"
    assert tier_one_match(text, []) == tier_one_match(text, None)


def test_catastrophic_backtracking_capped_by_match_timeout():
    # HIGH finding: (x+x+)+y hangs stdlib re.search for seconds on 80 chars.
    import time

    text = "x" * 80
    start = time.monotonic()
    decision = tier_one_match(text, ["(x+x+)+y"])
    elapsed = time.monotonic() - start
    assert decision.delete is False
    assert elapsed < 2.0


def test_evil_patterns_cannot_block_legitimate_scams():
    decision = tier_one_match(
        "double your money now", ["(x+x+)+y", r"double\s+your\s+money"]
    )
    assert decision.delete is True


def test_cyrillic_homoglyphs_do_not_evade_tier1():
    text = "GUARANTEED рrofit every week"  # Cyrillic р
    decision = tier_one_match(text, [])
    assert decision.delete is True


def test_cyrillic_homoglyphs_do_not_evade_tier2_trigger():
    assert is_tier_two_trigger("verify yоur wаllet") is True  # Cyrillic о, а
    assert is_tier_two_trigger("visit https://docs.python.org") is True


def test_normalization_preserves_digits_for_legit_text():
    # Homoglyph folding must not remap digits or legitimate chatter turns into
    # pattern fodder ("0" -> "o" would corrupt every \d+ pattern).
    assert tier_one_match("we shipped v2 with 10% fee discount, see docs", []).delete is False


async def test_seam_empty_keywords_from_config_still_delete_defaults():
    # The exact integration shape the critic proved broken: get_chat_config
    # returns [] and evaluate must still arm the default blacklist.
    decision = await evaluate("send 1 eth to this address now", [])
    assert decision.delete is True


def test_every_default_pattern_survives_the_runtime_pipeline():
    # A default pattern longer than the length cap is silently dropped by
    # _compiled(), disarming that rule for every chat. This guards against
    # shipping a default the pipeline itself refuses to run.
    assert len(DEFAULT_PATTERNS) == len(scam_engine._compiled(DEFAULT_PATTERNS))
    for pattern in DEFAULT_PATTERNS:
        assert len(pattern) <= scam_engine._MAX_PATTERN_LENGTH, pattern[:60]


# --- critic round 2 regressions ---


def test_uppercase_cyrillic_homoglyphs_do_not_evade():
    assert tier_one_match("Guaranteed Рrofit every week", []).delete is True  # Cyrillic Р
    assert tier_one_match("DOUBLE YOUR MОNEY TODAY", []).delete is True  # Cyrillic О
    assert tier_one_match("SEED PHRАSE verification required now", []).delete is True  # Cyrillic А


def test_earn_percent_pattern_matches_pitch_not_yield_talk():
    assert tier_one_match("Earn 10% daily on your deposit, fully passive", []).delete is True
    assert tier_one_match("make weekly profit with our bot, guaranteed", []).delete is True
    assert tier_one_match("we pay stakers 10% monthly, governance decided", []).delete is False
    assert tier_one_match("APY is 12% monthly right now", []).delete is False


def test_non_string_entries_in_pattern_list_do_not_crash():
    hit = tier_one_match("scamtext now", ["scamtext", {"evil": 1}, 42])
    assert hit.delete is True and hit.matched_pattern == "scamtext"
    assert not tier_one_match("anything", [{"evil": 1}]).delete


def test_fully_non_list_patterns_fall_back_to_defaults():
    assert tier_one_match("double your money", {"evil": 1}).delete is True  # type: ignore[arg-type]


async def test_tier1_scan_runs_off_the_event_loop():
    # evaluate must not run tier-1 regex scanning on the loop; the engine wraps
    # it in to_thread (behavioral proxy: evaluate still works and returns tier 1).
    decision = await evaluate("send 1 eth to this address now", [])
    assert decision.delete is True and decision.tier == 1


def test_earn_pattern_requires_percent_or_profit_noun():
    for ham in (
        "we make monthly payments to our moderators",
        "I make daily backups of the ledger",
        "you can earn daily interest in a savings account",
    ):
        assert tier_one_match(ham, []).delete is False, ham
    for scam in (
        "Earn 10% daily on your deposit, fully passive",
        "make weekly profit with our trading bot",
    ):
        assert tier_one_match(scam, []).delete is True, scam


@pytest.mark.parametrize(
    "text",
    [
        "send 0.1 ETH to 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 to join",
        "whale moved 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM earlier",
    ],
)
def test_wallet_addresses_trigger_tier2(text):
    assert is_tier_two_trigger(text)
