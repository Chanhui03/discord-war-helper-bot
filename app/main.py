import logging

from alembic import command
from alembic.config import Config

from app.bot.client import WarBot
from app.config.settings import ROOT, settings

def migrate() -> None:
    """기동할 때마다 스키마를 최신으로 맞춘다. 첫 실행이면 DB 파일이 만들어진다."""
    command.upgrade(Config(ROOT / "alembic.ini"), "head")

def main() -> None:
    migrate()
    # migrate() 가 root 에 붙인 alembic 콘솔 핸들러를 걷는다. 그대로 두면
    # discord.py 가 붙이는 핸들러와 겹쳐 모든 줄이 두 번 찍힌다.
    logging.getLogger().handlers.clear()
    bot = WarBot()
    bot.run(settings.discord_token, root_logger=True)

if __name__ == "__main__":
    main()
