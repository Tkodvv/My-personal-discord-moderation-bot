#!/usr/bin/env python3
"""
Discord Moderation Bot Entry Point
Main script to start the Discord bot with proper error handling and logging.
"""

import asyncio
import logging
import os
import sys
import discord  # <-- added
from dotenv import load_dotenv

from bot import DiscordBot
from utils.logging_config import setup_logging

# Load environment variables
load_dotenv()

DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")  # optional: instant slash updates in one server

async def run_bot(discord_token: str):
    """Create the bot, load cogs, sync slash commands, and start."""
    bot = DiscordBot()

    # Load your admin cog (contains the hybrid /alt + !alt)
    try:
        await bot.load_extension("cogs.admin")
    except Exception as e:
        logging.getLogger(__name__).error("Failed to load cogs.admin: %s", e)
        raise

    # Sync slash commands (instant if DEV_GUILD_ID is set)
    try:
        if DEV_GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=int(DEV_GUILD_ID)))
            logging.getLogger(__name__).info("Slash commands synced to dev guild %s", DEV_GUILD_ID)
        else:
            await bot.tree.sync()
            logging.getLogger(__name__).info("Slash commands synced globally (may take time to appear)")
    except Exception as e:
        logging.getLogger(__name__).warning("Slash sync failed: %s", e)

    await bot.start(discord_token)

def main():
    """Main function to start the Discord bot."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Get Discord token from environment
    discord_token = os.getenv('DISCORD_TOKEN')
    if not discord_token:
        logger.error("DISCORD_TOKEN environment variable not found!")
        logger.error("Please set your Discord bot token in the .env file or environment variables.")
        sys.exit(1)
    
    # Run the bot (async) so we can load cogs & sync before start
    try:
        logger.info("Starting Discord Moderation Bot...")
        asyncio.run(run_bot(discord_token))
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
