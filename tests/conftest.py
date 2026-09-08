import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.database.base import Base

@pytest.fixture(autouse=True)
def no_network():
    """테스트가 op.gg 로 나가지 않게 막는다.

    최고 티어 백필은 남의 사이트를 부르므로 기본값이 켜져 있어도 여기서는 끈다.
    파싱 자체는 저장해 둔 응답으로 test_opgg.py 에서 따로 본다.
    """
    previous = settings.opgg_backfill
    settings.opgg_backfill = False
    yield
    settings.opgg_backfill = previous

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
