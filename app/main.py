from alembic import command
from alembic.config import Config

from app.bot.client import WarBot
from app.config.settings import ROOT, settings

def migrate() -> None:
    """기동할 때마다 스키마를 최신으로 맞춘다. 첫 실행이면 DB 파일이 만들어진다."""
    command.upgrade(Config(ROOT / "alembic.ini"), "head")

def main() -> None:
    migrate()
    bot = WarBot()
    bot.run(settings.discord_token, root_logger=True)

if __name__ == "__main__":
    main()
