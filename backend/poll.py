"""Local development runner: long polling instead of webhooks.

Usage (from backend/): .venv/bin/python poll.py
"""
from __future__ import annotations

import logging

from telegram.ext import ApplicationBuilder

import bot
import config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        settings = config.load_config()
    except config.ConfigError as exc:
        raise SystemExit(f"poll: {exc}") from exc
    if not settings.telegram_bot_token:
        raise SystemExit("poll: TELEGRAM_BOT_TOKEN is not set")
    application = (
        ApplicationBuilder().token(settings.telegram_bot_token).concurrent_updates(True).build()
    )
    bot.register_handlers(application)
    application.run_polling(allowed_updates=["message", "my_chat_member"])


if __name__ == "__main__":
    main()
