"""Database engine, session and Base class."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from .config import settings


def database_url(url: str) -> str:
    """Hosts like Neon/Vercel give 'postgres://…' or 'postgresql://…'; SQLAlchemy needs the driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_url = database_url(settings.database_url)
_kwargs = {"pool_pre_ping": True}
if os.getenv("VERCEL"):
    # Serverless: instances are frozen between requests, so don't keep a pool of connections;
    # Neon's connection pooler (PgBouncer) does the pooling. It also can't use prepared statements.
    _kwargs = {"poolclass": NullPool, "connect_args": {"prepare_threshold": None}}
elif "-pooler." in _url:
    # Neon's pooled address (used e.g. when seeding the hosted database from a laptop)
    _kwargs["connect_args"] = {"prepare_threshold": None}
elif _url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in _url:
        _kwargs["poolclass"] = StaticPool  # one shared in-memory DB (used by tests)

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables that don't exist yet. (Switch to Alembic once the schema settles.)"""
    from . import models  # noqa: F401  - registers the tables
    Base.metadata.create_all(bind=engine)
