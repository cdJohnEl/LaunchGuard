# Backend internal API (backend modules must conform exactly)

This is the seam between `firebase_client.py` / `scam_engine.py` / `llm_service.py`
(data layer) and `bot.py` / `main.py` (consumers). Signatures are the contract.

## `firebase_client.py`

```python
def init_firebase() -> None
    # Idempotent. Reads GOOGLE_APPLICATION_CREDENTIALS (path to service account
    # JSON) or FIREBASE_SERVICE_ACCOUNT_JSON (raw JSON string). Raises
    # FirebaseConfigError with an actionable message if neither is present.
def is_ready() -> bool  # True after successful init
def close() -> None

async def ensure_chat(chat_id: int, group_name: str, chat_type: str) -> None
    # merge-create the group doc with contract defaults; never overwrites
    # scams_blocked or faq_pairs.
async def set_chat_active(chat_id: int, active: bool) -> None
async def increment_scams_blocked(chat_id: int, amount: int = 1) -> None
    # firestore.Increment, atomic.
async def get_chat(chat_id: int) -> dict | None

async def get_chat_config(chat_id: int) -> dict
    # Returns {"scam_keywords": [...], "faq_pairs": {...}} with per-chat TTL
    # cache (>= 30s) so the hot message path does not read Firestore per message.
    # Missing fields fall back to empty defaults. Safe to call before init? No:
    # requires init; raises if not ready.

async def set_faq_pair(chat_id: int, keyword: str, response: str) -> None
async def delete_faq_pair(chat_id: int, keyword: str) -> None
```

All Firestore I/O is sync google-cloud calls wrapped in `asyncio.to_thread`.
Never block the event loop.

## `scam_engine.py`

```python
DEFAULT_PATTERNS: list[str]  # >= 12 case-insensitive regexes, blatant scams only

def tier_one_match(text: str, patterns: list[str] | None = None) -> Decision
    # patterns=None -> DEFAULT_PATTERNS. Invalid regex entries are skipped
    # (patterns come from Firestore, cannot be trusted). Return Decision
    # (delete=True, tier=1) on first match.
def is_tier_two_trigger(text: str) -> bool
    # True if text contains a URL (http(s)://, www., t.me/), the word
    # "wallet"/"wallets" (word boundary; must NOT match "walletconnect"), or a
    # wallet address (0x + 40 hex, or 33-44 char base58) per the PRD.
async def evaluate(text: str, patterns: list[str] | None = None) -> Decision
    # Tier 1 first; if clean and tier-2 trigger -> llm_service.check_intent;
    # LLM error/timeout -> Decision(delete=False) (fail-open), never raise.
```

## `llm_service.py`

```python
async def check_intent(text: str) -> ScamVerdict  # from contracts.schema
    # Dispatches to the provider named by LAUNCHGUARD_LLM_PROVIDER (default "mock").
    # Raises UnknownProviderError for unregistered names.
```

Providers:
- `mock` (default): deterministic heuristic placeholder, no network.
- `groq`: hosted Groq chat completions (OpenAI-compatible, JSON mode, httpx),
  env `GROQ_API_KEY` + optional `GROQ_MODEL` (default `openai/gpt-oss-20b`).
- `claude_cli`: shells out to local `claude -p`.
- `openai_check_intent(text, api_key) -> ScamVerdict` and `gemini_check_intent(...)`:
  stubs that raise NotImplementedError with fill-me-in instructions.

LLM calls get a timeout (default 10s, env `LLM_TIMEOUT_SECONDS`).
