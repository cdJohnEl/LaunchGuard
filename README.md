# Launch Guard

Centralized Telegram moderation for Web3 founder groups. One shared bot
(`@LaunchGuardBot`) gets added to a group as admin; it deletes scams with a
two-tier engine (deterministic blacklist, then LLM intent check on link/wallet
messages), auto-answers configured FAQ keywords, and reports a live
"Scams Blocked" counter to a Next.js dashboard.

```
LaunchGuard/
├── contracts/            shared schema (Python + markdown, the single source of truth)
├── backend/
│   ├── bot.py            python-telegram-bot v21 handlers (Application, async)
│   ├── main.py           FastAPI webhook server (lifespan boots the bot)
│   ├── poll.py           local-dev alternative: long polling, no webhook needed
│   ├── scam_engine.py    tier 1 (regex) + tier 2 dispatch + trigger detection
│   ├── llm_service.py    pluggable LLM providers (mock default, claude_cli, openai/gemini stubs)
│   ├── firebase_client.py Firestore data layer (async wrappers, TTL cache)
│   ├── config.py         env parsing
│   ├── tests/            gate tests (offline, deterministic, < 3s)
│   └── evals/            labeled scam/ham dataset + precision/recall harness
├── frontend/             Next.js App Router dashboard (Tailwind, Firebase Client SDK)
└── firestore.rules       locked-down rules (Google auth + proof-of-control claims)
```

## Prerequisites

- Python 3.11+ (developed on 3.12), Node 18.17+
- A Telegram bot token (talk to @BotFather)
- A Firebase project with Firestore created

## Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill it in
```

Environment variables (see `backend/.env.example`):

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | from @BotFather |
| `GOOGLE_APPLICATION_CREDENTIALS` | yes (or the JSON var below) | path to the Firebase service-account JSON |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | alternative to the path above | full service-account JSON as one string (handy on Railway/Render) |
| `WEBHOOK_URL` | for webhook mode | public HTTPS base URL, no trailing slash |
| `TELEGRAM_WEBHOOK_SECRET` | recommended | random string Telegram echoes in a header; `openssl rand -hex 32` |
| `LAUNCHGUARD_LLM_PROVIDER` | no (default `mock`) | `mock`, `groq`, or `claude_cli` |
| `LLM_TIMEOUT_SECONDS` | no (default 10) | tier-2 call timeout; on timeout the bot fails open (no delete) |
| `GROQ_API_KEY` | when provider is `groq` | from console.groq.com -> API keys |
| `GROQ_MODEL` | no (default `openai/gpt-oss-20b`) | any Groq-hosted model id |

### Running

Webhook mode (production):

```bash
cd backend
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Expose it publicly, e.g. `ngrok http 8000`, set `WEBHOOK_URL=https://<your-host>`
in `.env`, and restart the server. The app calls `set_webhook` on boot, so the
bot starts receiving updates without any manual Telegram steps. Run **one**
uvicorn worker; the in-process PTB Application is not multi-worker safe.

Local dev without a public URL:

```bash
cd backend
.venv/bin/python poll.py
```

Both modes register the same handlers. The server boots with zero env vars set
(degraded 503 paths) so you can smoke-test with `/healthz`.

### Tests and evals

```bash
cd backend
.venv/bin/pytest -q                          # 205 gate tests, ~2.5s, offline
.venv/bin/python evals/eval_scam_engine.py   # precision/recall on 92 labeled rows
```

The eval exits non-zero if scam recall < 0.85 or false-positive rate > 0.15.
Extend `backend/evals/dataset.jsonl` whenever the engine misses or wrongly
deletes something; the suite re-checks the whole dataset on every run.

## Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # paste the web SDK config from
                                   # Firebase console -> Project settings -> Your apps
npm run dev                        # http://localhost:3000 -> /dashboard
```

Paste the group's chat id (e.g. `-1001234567890`) into the dashboard, or set
`NEXT_PUBLIC_DEFAULT_CHAT_ID`. The counter updates live via an `onSnapshot`
listener on `groups/{chatId}`; the FAQ form writes `faq_pairs.{keyword}`
straight to Firestore.

```bash
npm run test    # vitest
npm run build   # production build
```

### Firestore rules (locked-down mode)

Groups are private to the founder who claimed them. The access model:

- The bot writes through the Admin SDK, which bypasses rules entirely.
- Founders sign in with Google (Firebase Auth) on the dashboard.
- **Claims are proof-of-control**: `/connect` shows the founder a command,
  they type `/claim <code>` in their Telegram group, and the bot binds
  `owner_uid` only after verifying the sender is a group ADMIN. The web
  client can never write `owner_uid`; the rules forbid it outright.
- Owned group docs are invisible to every other account; unowned docs are
  readable signed-in (the connect flow verifies ids). Nobody can list or
  delete groups. `public/stats` is the only world-readable doc (the
  landing's live totals).

Deploy the rules and enable the auth provider (both are console steps):

1. Firebase console -> Firestore -> Rules: paste `firestore.rules`, Publish.
   (Or `firebase login` once, then `firebase deploy --only firestore:rules`.)
2. Firebase console -> Authentication -> Sign-in method: enable **Google**.
3. Groups registered before claiming existed are claimable by their first
   admin to run `/claim`.

## Filling in the real LLM (tier 2)

Tier 2 ships with a deterministic mock provider. Your options:

1. `LAUNCHGUARD_LLM_PROVIDER=groq` — hosted Groq (OpenAI-compatible, JSON mode).
   Set `GROQ_API_KEY` (console.groq.com -> API keys) and optionally `GROQ_MODEL`
   (default `openai/gpt-oss-20b`, the low-latency pick; `openai/gpt-oss-120b`
   is the stronger classifier).
2. `LAUNCHGUARD_LLM_PROVIDER=claude_cli` — routes through the local Claude Code
   CLI (`claude -p`), no API key or hosted API involved.
3. `openai_check_intent` / `gemini_check_intent` in `backend/llm_service.py` —
   stubs raising `NotImplementedError` with exact instructions in their
   docstrings.

The user message is framed as untrusted content between `<message>` tags for
every provider, and any provider error or timeout fails open (no delete).

## What to restart after changes

| Changed | Restart with |
| --- | --- |
| any `backend/*.py` | kill and rerun `uvicorn main:app` (or `poll.py`) |
| `WEBHOOK_URL` / bot token | rerun the server; webhook re-registers on boot |
| `frontend/**` | `npm run dev` hot-reloads; for prod rerun `npm run build && npm start` |
| `firestore.rules` | `firebase deploy --only firestore:rules` (no process restart) |

## Known gaps (by design, MVP scope)

- Any signed-in Google account can read a single UNOWNED group doc by id (the
  connect flow verifies ids before claiming); owned docs are invisible to
  everyone but their owner. Unowned docs are therefore readable signed-in
  until claimed — claim early.
- A group co-admin can run `/claim` and bind the group to their own founder
  account: Telegram admin rights are the trust boundary, by design.
- Edited messages are ignored entirely (they are a spam vector, not scanned).
- FAQ matching is literal keyword-in-message (word boundary, case-insensitive);
  no fuzzy or embedding matching yet.
- Unicode confusables are folded for a fixed homoglyph table (Cyrillic/Greek
  lookalikes, case-folded); it is not a full Unicode confusables implementation.
- If you change `TELEGRAM_WEBHOOK_SECRET`, restart the server so `set_webhook`
  re-registers with the new secret; a stale webhook + new env value 403s every
  update.
- The `claude_cli` provider forwards message text into the model prompt; a
  crafted message can try to steer the verdict. The prompt demands JSON-only
  output and the parser rejects anything else, but treat LLM moderation as
  probabilistic: tier 2 fails open on any error or timeout.
- Anonymous admins (Telegram's GroupAnonymousBot sender) and linked-channel
  posts are not moderated: anonymous senders are admins by definition, and
  channel posts are controlled by the group owner.
- A base58-looking token of 33-44 characters in ordinary chatter triggers one
  tier-2 intent check (which fails open); this costs a model call, never a
  false deletion.

