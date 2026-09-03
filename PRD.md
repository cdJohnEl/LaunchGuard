쓸**Product Requirements Document (PRD): Launch Guard MVP**

### 1. Product Overview

Launch Guard is a Telegram community protection SaaS designed for Web3 founders. Instead of requiring users to supply their own bot tokens, Launch Guard relies on a single, centralized bot (`@LaunchGuardBot`) that users add to their groups as an admin. The system uses a two-tier moderation engine (Regex/Keyword filtering + AI Intent analysis) and logs all actions to a custom dashboard where founders can monitor "Scams Blocked" in real-time.

### 2. Architecture & Tech Stack

* **Backend (Bot & API):** Python 3.11+, `python-telegram-bot` (v20+ async), and FastAPI for handling webhook routing and frontend API requests.
* **Database:** Firebase Firestore (NoSQL). Perfect for unstructured Telegram message logs, dynamic FAQ maps, and fast counter updates.
* **AI Engine (Tier 2):** OpenAI (`gpt-4o-mini`), Gemini (`gemini-1.5-flash`), or Anthropic (`claude-3-haiku`) for ultra-low latency intent classification.
* **Frontend (Dashboard):** Next.js (App Router), React, Tailwind CSS, and Firebase Client SDK for real-time listener updates.
* **Hosting:**
* Backend: Railway, Render, or DigitalOcean (needs persistent connection for webhooks/polling).
* Frontend: Vercel.



### 3. Core MVP Features

* **Centralized Bot Provisioning:** Users do not need to speak to BotFather. They simply add `@LaunchGuardBot` to their Telegram group, give it admin rights (delete messages, ban users), and the bot automatically registers the `chat_id` in Firestore via a `ChatMemberUpdated` event.
* **Two-Tier Scam Detection Engine:**
* *Tier 1 (Deterministic):* Hardcoded regex matching for crypto scams (e.g., "send to this address", fake domains, unapproved Telegram links). Immediate deletion.
* *Tier 2 (AI Intent):* If Tier 1 passes but the message contains a link, image, or wallet address, it triggers a fast LLM evaluation ("Does this message intend to scam, phish, or execute a FUD campaign?").


* **Auto-Responder:** Listens for exact keyword matches (e.g., "contract address", "wen launch") and replies with predefined text configured in the dashboard.
* **Live Dashboard:** A web interface where founders sign in, select their connected group, configure custom FAQ keywords, and view a live-updating "Scams Blocked" metric.

### 4. Data Schema (Firestore)

* **Collection:** `groups`
* `chat_id` (String/Int, Document ID)
* `owner_uid` (String, links to the user who registered it)
* `group_name` (String)
* `scam_keywords` (Array of Strings)
* `faq_pairs` (Map/Dict: `{ "keyword": "response" }`)
* `scams_blocked` (Integer)
* `subscription_status` (String: "trial", "active")



---
