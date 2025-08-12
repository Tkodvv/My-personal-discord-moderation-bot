#!/usr/bin/env python3
"""
Discord Moderation Bot Entry Point
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

from bot import DiscordBot
from utils.logging_config import setup_logging

load_dotenv()

async def run_bot(discord_token: str):
    bot = DiscordBot()
    try:
        await bot.start(discord_token)
    finally:
        # avoids "Unclosed connector" if something blows up
        await bot.close()

def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN environment variable not found!")
        sys.exit(1)

    try:
        logger.info("Starting Discord Moderation Bot...")
        asyncio.run(run_bot(token))
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
