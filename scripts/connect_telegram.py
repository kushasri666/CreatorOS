"""Run manually in your terminal. Never share login codes or session files."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main():
    session = os.getenv("TELEGRAM_SESSION_PATH", "data/telegram")
    Path(session).parent.mkdir(parents=True, exist_ok=True)
    async with TelegramClient(session, int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"]) as client:
        print("Telegram local session authorized:", await client.is_user_authorized())
        print("Keep the session file private. This script does not send messages or collect metrics.")


if __name__ == "__main__":
    asyncio.run(main())
