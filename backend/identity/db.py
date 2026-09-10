"""Engine and session plumbing.

The engine is created on first use rather than at import, so importing the
package (for a migration, a seed, a unit test) never demands a live database.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from . import config

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        url = config.database_url()
        if url.startswith("sqlite"):
            # The unit tests run on an in-memory SQLite; every connection to
            # ":memory:" would otherwise be a different empty database.
            _engine = create_engine(
                url, poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_engine(url, pool_pre_ping=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    engine()
    assert _factory is not None
    return _factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def reset() -> None:
    """Forget the engine so the next use re-reads DATABASE_URL. Tests only."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None
