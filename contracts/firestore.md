# Firestore contract (source of truth)

## Collection: `groups`

Document ID: `str(chat_id)` (e.g. `"-1001234567890"`). One document per Telegram group the bot is in.

| Field                 | Type                 | Notes                                                          |
| --------------------- | -------------------- | -------------------------------------------------------------- |
| `chat_id`             | int                  | Telegram chat id                                               |
| `group_name`          | string               | Title at registration time                                     |
| `owner_uid`           | string \| null       | Firebase Auth uid of the founder. `null` until auth exists     |
| `active`              | bool                 | Bot present in the group (false after kicked/left)             |
| `subscription_status` | "trial" \| "active"  | Defaults to `"trial"`                                          |
| `scams_blocked`       | int                  | Incremented by 1 on every successfully deleted scam            |
| `scam_keywords`       | string[]             | Per-chat tier-1 blacklist (regex). `[]` -> engine defaults     |
| `faq_pairs`           | map<string, string>  | `{ keyword: response }`, powers the auto-responder             |
| `created_at`          | string (ISO-8601 UTC)|
| `updated_at`          | string (ISO-8601 UTC)|

## faq_pairs semantics

- Key: the trigger keyword/phrase as configured in the dashboard (e.g. `"contract address"`).
- Value: the exact response the bot sends when a member message contains that keyword (case-insensitive, word-boundary match).
- Dashboard writes a pair with `updateDoc(ref, { ["faq_pairs." + keyword]: response })`.

## Counter semantics

- `scams_blocked` is only incremented AFTER a message delete succeeds.
- Backend uses `firestore.Increment(1)` (atomic), never read-modify-write.
- Dashboard reads it live via `onSnapshot`.

## Rules

`firestore.rules` at the repo root is intentionally open for local development.
Lock it down before any production deploy (see README, "Locking down Firestore").
