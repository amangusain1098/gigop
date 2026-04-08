from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ..config import GigOptimizerConfig
from .models import Base


class DatabaseManager:
    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        connect_args = {"check_same_thread": False} if config.database_url.startswith("sqlite") else {}
        self.engine = create_engine(
            config.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
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
