"""SQLAlchemy 异步引擎、会话与建表逻辑。

PostgreSQL 与 SQLite 都可用：JSON 结构（曲线点、馏分方案）统一以
JSON 列存储，PostgreSQL 用原生 JSONB，SQLite 退化为 TEXT(JSON)。
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from sqlalchemy import Dialect, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class JSONLike(TypeDecorator):
    """跨后端的 JSON 列：PG 上为 JSONB，其它后端为 TEXT。"""

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        return json.loads(value)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    from . import models  # noqa: F401  确保模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量兼容：旧的本地 SQLite 库（create_all 不会 ALTER 已有表）
        # 缺少 plans.thresholds 列时补上，旧方案按“未设置阈值”处理。
        if engine.dialect.name == "sqlite":
            await conn.run_sync(_ensure_sqlite_columns)


def _ensure_sqlite_columns(sync_conn) -> None:
    from sqlalchemy import inspect, text

    cols = {c["name"] for c in inspect(sync_conn).get_columns("plans")}
    if cols and "thresholds" not in cols:
        sync_conn.execute(text("ALTER TABLE plans ADD COLUMN thresholds JSON"))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
