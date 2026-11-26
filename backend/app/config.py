"""App settings, read from environment variables (or a .env file in backend/)."""
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv is optional
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = _env("DATABASE_URL", "postgresql+psycopg://planora:planora@localhost:5432/planora")
    secret_key: str = _env("SECRET_KEY", "change-me")
    token_expire_minutes: int = int(_env("TOKEN_EXPIRE_MINUTES", "10080"))
    cors_origins: list[str] = field(default_factory=lambda: _list(_env("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")))

    gemini_api_key: str = _env("GEMINI_API_KEY")
    gemini_model: str = _env("GEMINI_MODEL", "gemini-3.5-flash")
    # Backups, in order, used when the main model is overloaded (503) or rate-limited (429).
    # Comma-separated; empty = no backups.
    gemini_fallback_models: list[str] = field(default_factory=lambda: _list(
        _env("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-flash-lite-latest")))
    # Longest wait for one Gemini reply, and for the whole breakdown including retries.
    # While models are busy, Planora keeps cycling through them until about LLM_TOTAL_SECONDS - 5.
    # The total stays under Vercel's 60 s request limit so the user always gets an answer.
    llm_timeout_seconds: float = float(_env("LLM_TIMEOUT_SECONDS", "35"))
    llm_total_seconds: float = float(_env("LLM_TOTAL_SECONDS", "50"))

    # A missed end-of-day review can still be filled in for this many days.
    # Older unreviewed days count as "not done" and their work is rescheduled.
    review_lookback_days: int = int(_env("REVIEW_LOOKBACK_DAYS", "3"))

    today_override: str = _env("PLANORA_TODAY")
    # Time zone for "today", missed days and reminder times, e.g. "Asia/Kolkata".
    # Empty = the computer's own local time (fine on a laptop; servers usually run on UTC).
    timezone: str = _env("APP_TIMEZONE")
    frontend_dir: str = _env("FRONTEND_DIR", str(Path(__file__).resolve().parent.parent.parent / "frontend"))


settings = Settings()


def _local_now() -> datetime:
    """Current date-time in APP_TIMEZONE (or the machine's local time), without tz info."""
    if settings.timezone:
        return datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    return datetime.now()


def now() -> datetime:
    """Local date-time, shifted to PLANORA_TODAY when that is set."""
    current = _local_now()
    if settings.today_override:
        d = date.fromisoformat(settings.today_override)
        current = current.replace(year=d.year, month=d.month, day=d.day)
    return current


def today() -> date:
    """The app's idea of today. Uses PLANORA_TODAY when set (for demos/tests)."""
    return date.fromisoformat(settings.today_override) if settings.today_override else _local_now().date()
