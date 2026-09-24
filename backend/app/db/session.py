from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# poolclass=NullPool is load-bearing, not a style choice -- this module is
# imported once and its `engine` is shared by both the FastAPI process and
# every Celery worker task. FastAPI is fine with a normal pool (one event
# loop for the process lifetime), but each Celery task execution wraps its
# async work in its own asyncio.run(), which spins up and tears down a
# distinct event loop every single call. asyncpg connections are physically
# bound to the event loop that created them, so a normal pool will, on any
# retry (a second, independent asyncio.run() = a new loop), hand back a
# connection created on a now-dead loop and raise
# `asyncpg.exceptions.InterfaceError: cannot perform operation: another
# operation is in progress` or `AttributeError: 'NoneType' object has no
# attribute 'send'`. Reproduced in production logs, twice, before this fix.
# NullPool makes every checkout a fresh connection and closes it on
# checkin instead of pooling it, so no connection ever survives past the
# asyncio.run() call that created it -- eliminating the cross-loop reuse
# entirely. The small per-call connection overhead this adds is a
# non-issue at this app's scale (a single VPS, not high QPS).
engine = create_async_engine(settings.database_url, echo=False, future=True, poolclass=NullPool)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields a DB session, closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session
