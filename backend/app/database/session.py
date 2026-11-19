"""
CareBridge Database Base & Session Management
Supports Async SQLAlchemy 2.0 sessions for FastAPI/LangGraph and Sync engine for migrations/seeding.
"""

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)
from sqlalchemy.types import Uuid, DateTime
from app.core.config import settings

# Naming convention for foreign keys and constraints
POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}
metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class TimestampedUUIDMixin:
    """Standard mixin providing a UUID primary key and timezone-aware UTC audit timestamps."""
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )


import os
from pathlib import Path

# Configure Async and Sync Database URLs
db_file = Path("C:/CareBridge/backend/carebridge.db").resolve()
raw_db_url = settings.DATABASE_URL or f"sqlite+aiosqlite:///{db_file.as_posix()}"

# Normalize postgresql:// and sqlite:// for SQLAlchemy async engine
if raw_db_url.startswith("postgresql://"):
    ASYNC_DB_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_db_url.startswith("sqlite://") and "+aiosqlite" not in raw_db_url:
    ASYNC_DB_URL = raw_db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
else:
    ASYNC_DB_URL = raw_db_url

# If in automated test mode without PostgreSQL explicitly requested, use local persistent SQLite
if "postgres" in ASYNC_DB_URL and (os.getenv("TESTING") == "1" and not os.getenv("FORCE_POSTGRES")):
    ASYNC_DB_URL = f"sqlite+aiosqlite:///{db_file.as_posix()}"

SYNC_DB_URL = ASYNC_DB_URL.replace("+asyncpg", "").replace("+aiosqlite", "")

# Create engines with connection pooling
connect_args = {"check_same_thread": False} if "sqlite" in SYNC_DB_URL else {}
async_connect_args = {"check_same_thread": False} if "sqlite" in ASYNC_DB_URL else {}

# Pool configuration for high-concurrency healthcare endpoints
pool_kwargs = {}
if "postgres" in ASYNC_DB_URL:
    pool_kwargs = {
        "pool_size": 30,
        "max_overflow": 50,
        "pool_timeout": 60,
    }

async_engine = create_async_engine(
    ASYNC_DB_URL,
    echo=False,
    future=True,
    connect_args=async_connect_args,
    pool_pre_ping=True,
    **pool_kwargs
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

sync_pool_kwargs = {}
if "postgres" in SYNC_DB_URL:
    sync_pool_kwargs = {
        "pool_size": 30,
        "max_overflow": 50,
        "pool_timeout": 60,
    }

sync_engine = create_engine(
    SYNC_DB_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
    **sync_pool_kwargs
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

# Enable WAL mode and busy timeout for SQLite to avoid lock contention
from sqlalchemy import event

@event.listens_for(sync_engine, "connect")
def _set_sync_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in SYNC_DB_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

@event.listens_for(async_engine.sync_engine, "connect")
def _set_async_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in ASYNC_DB_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


def get_sync_db() -> Session:
    """Returns a new synchronous database session from the active factory."""
    return sync_session_factory()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for injecting an async database session into FastAPI route handlers."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
