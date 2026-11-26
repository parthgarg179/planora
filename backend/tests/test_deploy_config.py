"""Settings added for hosting (Vercel + Neon): database address, time zone, demo login."""
from datetime import datetime, timedelta, timezone

import pytest

from app import config
from app.database import database_url


def test_hosted_database_urls_get_the_psycopg_driver():
    neon = "postgres://user:pw@ep-x-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert database_url(neon) == "postgresql+psycopg://user:pw@ep-x-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"  # already fine
    assert database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_app_timezone_decides_today(monkeypatch):
    monkeypatch.setattr(config, "settings", config.Settings(timezone="Asia/Kolkata", today_override=""))
    india_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    assert config.today() == india_now.date()
    assert abs((config.now() - india_now.replace(tzinfo=None)).total_seconds()) < 5


def test_today_override_still_wins(monkeypatch):
    monkeypatch.setattr(config, "settings", config.Settings(timezone="Asia/Kolkata", today_override="2026-01-05"))
    assert str(config.today()) == "2026-01-05"
    assert config.now().date().isoformat() == "2026-01-05"


def test_seed_refuses_without_demo_login(monkeypatch):
    from scripts import seed_demo
    monkeypatch.setattr(seed_demo, "DEMO_EMAIL", "")
    monkeypatch.setattr(seed_demo, "DEMO_PASSWORD", "")
    with pytest.raises(SystemExit):
        seed_demo.main()
