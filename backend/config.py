"""LaunchGuard backend configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    """A required environment variable is missing or malformed."""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    webhook_url: str
    webhook_secret: str
    llm_provider: str = "mock"
    llm_timeout_seconds: float = 10.0


_dotenv_loaded = False


def _load_dotenv() -> None:
    # backend/.env is the documented setup path (.env.example); never override real env vars.
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    _load_dotenv()
    value = os.environ.get(name, default)
    if isinstance(value, str):
        value = value.strip()
    return value


def load_config() -> Config:
    missing = [
        name
        for name in ("TELEGRAM_BOT_TOKEN", "WEBHOOK_URL", "TELEGRAM_WEBHOOK_SECRET")
        if not _env(name)
    ]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Fix: copy backend/.env.example to backend/.env, fill in the values, and restart the process "
            "(or export the variable(s) in the shell before starting)."
        )
    raw_timeout = _env("LLM_TIMEOUT_SECONDS", "10")
    try:
        timeout = float(raw_timeout)  # type: ignore[arg-type]
    except ValueError as exc:
        raise ConfigError(
            f"LLM_TIMEOUT_SECONDS={raw_timeout!r} is not a number. "
            "Fix: set LLM_TIMEOUT_SECONDS to seconds, e.g. 10."
        ) from exc
    return Config(
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", ""),
        webhook_url=_env("WEBHOOK_URL", ""),
        webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET", ""),
        llm_provider=_env("LAUNCHGUARD_LLM_PROVIDER", "mock") or "mock",
        llm_timeout_seconds=timeout,
    )


def google_credentials_path() -> Optional[str]:
    value = _env("GOOGLE_APPLICATION_CREDENTIALS")
    return value or None


def google_credentials_json() -> Optional[str]:
    value = _env("FIREBASE_SERVICE_ACCOUNT_JSON")
    return value or None


def llm_provider() -> str:
    return _env("LAUNCHGUARD_LLM_PROVIDER", "mock") or "mock"


def llm_timeout_seconds() -> float:
    raw = _env("LLM_TIMEOUT_SECONDS", "10")
    try:
        return float(raw)  # type: ignore[arg-type]
    except ValueError as exc:
        raise ConfigError(
            f"LLM_TIMEOUT_SECONDS={raw!r} is not a number. "
            "Fix: set LLM_TIMEOUT_SECONDS to seconds, e.g. 10."
        ) from exc
