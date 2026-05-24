from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_dotenv()


def env(name: str, fallback: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return fallback
    return value


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def int_env(name: str, fallback: int) -> int:
    value = env(name)
    if not value:
        return fallback

    try:
        return int(value)
    except ValueError:
        return fallback


def csv_env(name: str, fallback: list[str]) -> list[str]:
    value = env(name)
    if not value:
        return fallback

    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def resolve_telegram_webhook_url(
    *,
    telegram_webhook_url: str,
    public_base_url: str,
    render_external_url: str,
) -> str:
    if telegram_webhook_url:
        return telegram_webhook_url

    base_url = public_base_url or render_external_url
    if not base_url:
        return ""

    return f"{base_url.rstrip('/')}/telegram/webhook"


@dataclass(frozen=True, slots=True)
class Config:
    port: int
    telegram_bot_token: str
    telegram_webhook_url: str
    telegram_webhook_secret: str
    telegram_bot_mode: str
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    openai_model: str
    transcription_model: str
    transcript_languages: list[str]
    llm_chat_completions_url: str
    llm_api_key: str
    llm_model: str
    youtube_proxy_url: str
    youtube_http_proxy_url: str
    youtube_https_proxy_url: str
    youtube_cookies_file: str
    quiz_size: int


def load_config() -> Config:
    default_bot_mode = "webhook"
    return Config(
        port=int_env("PORT", 3000),
        telegram_bot_token=require_env("TELEGRAM_BOT_TOKEN"),
        telegram_webhook_url=resolve_telegram_webhook_url(
            telegram_webhook_url=env("TELEGRAM_WEBHOOK_URL", "") or "",
            public_base_url=env("PUBLIC_BASE_URL", "") or "",
            render_external_url=env("RENDER_EXTERNAL_URL", "") or "",
        ),
        telegram_webhook_secret=env("TELEGRAM_WEBHOOK_SECRET", "") or "",
        telegram_bot_mode=env("TELEGRAM_BOT_MODE", default_bot_mode) or default_bot_mode,
        supabase_url=require_env("SUPABASE_URL"),
        supabase_service_role_key=require_env("SUPABASE_SERVICE_ROLE_KEY"),
        openai_api_key=env("OPENAI_API_KEY", "") or "",
        openai_model=env("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
        transcription_model=env("TRANSCRIPTION_MODEL", "whisper-1") or "whisper-1",
        transcript_languages=csv_env("TRANSCRIPT_LANGUAGES", ["en"]),
        llm_chat_completions_url=env("LLM_CHAT_COMPLETIONS_URL", "") or "",
        llm_api_key=env("LLM_API_KEY", "") or "",
        llm_model=env("LLM_MODEL", "") or "",
        youtube_proxy_url=env("YOUTUBE_PROXY_URL", "") or "",
        youtube_http_proxy_url=env("YOUTUBE_HTTP_PROXY_URL", "") or "",
        youtube_https_proxy_url=env("YOUTUBE_HTTPS_PROXY_URL", "") or "",
        youtube_cookies_file=env("YOUTUBE_COOKIES_FILE", "") or "",
        quiz_size=int_env("QUIZ_SIZE", 7),
    )
