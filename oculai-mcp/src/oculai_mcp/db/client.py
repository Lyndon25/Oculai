"""PostgreSQL connection pool with LISTEN/NOTIFY support. (Adapted from Phase7)"""

import asyncio
import logging
from typing import Any

import asyncpg

from oculai_mcp.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()

    if _pool is not None and not _pool._closed and _pool_loop is current_loop:
        return _pool

    if _pool is not None and not _pool._closed:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None

    settings = get_settings()
    dsn = str(settings.db_url)
    logger.info("Creating database connection pool")
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        command_timeout=60,
        init=_init_connection,
    )
    _pool_loop = current_loop
    return _pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    import json

    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def close_db_pool() -> None:
    global _pool
    if _pool is not None and not _pool._closed:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None


async def execute_with_retry(query: str, *args: Any, max_retries: int = 3, base_delay: float = 0.5) -> str:
    pool = await get_db_pool()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError,
                asyncpg.SerializationError, asyncpg.DeadlockDetectedError) as e:
            last_error = e
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection error (attempt %d/%d), retrying in %.1fs", attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
    raise last_error or RuntimeError("Max retries exceeded")


async def fetch_with_retry(query: str, *args: Any, max_retries: int = 3, base_delay: float = 0.5) -> list[asyncpg.Record]:
    pool = await get_db_pool()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError,
                asyncpg.SerializationError, asyncpg.DeadlockDetectedError) as e:
            last_error = e
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection error (attempt %d/%d), retrying in %.1fs", attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
    raise last_error or RuntimeError("Max retries exceeded")


async def fetchval_with_retry(query: str, *args: Any, max_retries: int = 3, base_delay: float = 0.5) -> Any:
    pool = await get_db_pool()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError,
                asyncpg.SerializationError, asyncpg.DeadlockDetectedError) as e:
            last_error = e
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection error (attempt %d/%d), retrying in %.1fs", attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
    raise last_error or RuntimeError("Max retries exceeded")


async def fetchrow_with_retry(query: str, *args: Any, max_retries: int = 3, base_delay: float = 0.5) -> asyncpg.Record | None:
    pool = await get_db_pool()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError,
                asyncpg.SerializationError, asyncpg.DeadlockDetectedError) as e:
            last_error = e
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection error (attempt %d/%d), retrying in %.1fs", attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
    raise last_error or RuntimeError("Max retries exceeded")


class NotifyListener:
    """LISTEN/NOTIFY handler for cache invalidation."""

    def __init__(self) -> None:
        self._conn: asyncpg.Connection | None = None
        self._task: asyncio.Task[Any] | None = None
        self._handlers: dict[str, list[callable]] = {}

    def on(self, channel: str, handler: callable) -> None:
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)

    async def start(self) -> None:
        if self._conn is not None:
            return
        settings = get_settings()
        dsn = str(settings.db_url)
        self._conn = await asyncpg.connect(dsn)
        for channel in self._handlers:
            await self._conn.add_listener(channel, self._on_notify)
            await self._conn.execute(f"LISTEN {channel}")
            logger.info("Listening on channel: %s", channel)
        self._task = asyncio.create_task(self._keepalive())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._conn is not None:
            for channel in self._handlers:
                await self._conn.remove_listener(channel, self._on_notify)
            await self._conn.close()
            self._conn = None

    def _on_notify(self, conn: asyncpg.Connection, pid: int, channel: str, payload: str) -> None:
        for handler in self._handlers.get(channel, []):
            try:
                handler(payload)
            except Exception as e:
                logger.error("Error in notify handler for %s: %s", channel, e)

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(30)
            if self._conn is not None:
                try:
                    await self._conn.execute("SELECT 1")
                except Exception as e:
                    logger.warning("Keepalive failed: %s", e)


notify_listener = NotifyListener()
