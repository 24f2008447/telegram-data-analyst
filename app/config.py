"""
Central configuration. All secrets/config come from environment variables
so nothing sensitive is hardcoded in the repo.
"""
import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # Telegram
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = _env("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")

    # LLM (OpenAI-compatible)
    openai_api_key: str = _env("OPENAI_API_KEY")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4.1")
    openai_base_url: str = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Log hosting: we push each run's JSONL log to a public GitHub repo
    # using the GitHub Contents API, then link the raw.githubusercontent.com URL.
    github_token: str = _env("GITHUB_TOKEN")
    github_log_repo: str = _env("GITHUB_LOG_REPO")  # e.g. "yourname/telegram-bot-logs"
    github_log_branch: str = _env("GITHUB_LOG_BRANCH", "main")

    # Local paths
    local_log_dir: str = _env("LOCAL_LOG_DIR", "logs")
    download_dir: str = _env("DOWNLOAD_DIR", "/tmp/tda_downloads")

    # App
    port: int = int(_env("PORT", "8000"))
    env: str = _env("ENV", "development")


settings = Settings()
