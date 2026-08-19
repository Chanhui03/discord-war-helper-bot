from app.bot.client import WarBot
from app.config.settings import settings

def main() -> None:
    bot = WarBot()
    bot.run(settings.discord_token, root_logger=True)

if __name__ == "__main__":
    main()
