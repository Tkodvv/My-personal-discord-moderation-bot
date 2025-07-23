#!/usr/bin/env python3
"""
Discord Moderation Bot Entry Point
Main script to start the Discord bot with proper error handling and logging.
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

from bot import DiscordBot
from utils.logging_config import setup_logging

# Load environment variables
load_dotenv()

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
    
    # Create and run the bot
    try:
        bot = DiscordBot()
        logger.info("Starting Discord Moderation Bot...")
        bot.run(discord_token)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
