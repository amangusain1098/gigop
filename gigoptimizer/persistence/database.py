from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from ..config import GigOptimizerConfig
from .models import Base


class DatabaseManager:
    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        is_sqlite = config.database_url.startswith("sqlite")
        if is_sqlite:
            self._ensure_sqlite_parent_exists(config.database_url)
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        engine_kwargs = {
            "future": True,
            "pool_pre_ping": True,
            "connect_args": connect_args,
        }
        if is_sqlite:
            engine_kwargs["poolclass"] = NullPool
        self.engine = create_engine(
            config.database_url,
            **engine_kwargs,
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Session:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def healthcheck(self) -> tuple[bool, str]:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True, "database reachable"
        except Exception as exc:
            return False, str(exc)

    def _ensure_sqlite_parent_exists(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            return
        raw_path = database_url.removeprefix("sqlite:///")
        if not raw_path:
            return
        db_path = Path(raw_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
