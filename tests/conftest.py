import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base

@pytest_asyncio.fixture
async def session():
    """관계 적재 동작을 검증하기 위한 인메모리 세션.

    MissingGreenlet 류의 버그는 dialect 와 무관하게 재현되므로
    Postgres 없이도 돌 수 있도록 SQLite 를 쓴다.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as active:
        yield active

    await engine.dispose()
