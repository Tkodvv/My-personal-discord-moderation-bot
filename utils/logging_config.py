"""
Logging Configuration
Setup logging for the Discord bot with proper formatting and levels.
"""

import logging
import sys
from datetime import datetime

def setup_logging(level=logging.INFO):
    """
    Setup logging configuration for the bot.
    
    Args:
        level: Logging level (default: INFO)
    """
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    
    # Setup file handler for errors
    error_handler = logging.FileHandler('bot_errors.log', encoding='utf-8')
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Setup file handler for all logs
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(file_handler)
    
    # Configure discord.py logger to be less verbose
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)
    
    # Configure urllib3 logger to be less verbose
    urllib3_logger = logging.getLogger('urllib3')
    urllib3_logger.setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized")
    logger.info(f"Console logging level: {logging.getLevelName(level)}")
    logger.info(f"File logging enabled: bot.log (DEBUG), bot_errors.log (ERROR)")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Name for the logger
    
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)

class BotLogFilter(logging.Filter):
    """Custom log filter for bot-specific logging."""
    
    def filter(self, record):
        """Filter log records based on custom criteria."""
        # Add custom filtering logic here if needed
        return True

def log_command_usage(user: str, command: str, guild: str, success: bool = True):
    """
    Log command usage for analytics and monitoring.
    
    Args:
        user: Username who executed the command
        command: Command name
        guild: Guild name where command was executed
        success: Whether the command was successful
    """
    logger = logging.getLogger('command_usage')
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"{status} | {user} | {command} | {guild}")

def log_moderation_action(moderator: str, action: str, target: str, reason: str, guild: str):
    """
    Log moderation actions for audit purposes.
    
    Args:
        moderator: Username of the moderator
        action: Type of moderation action
        target: Target user/member
        reason: Reason for the action
        guild: Guild where action was performed
    """
    logger = logging.getLogger('moderation')
    logger.info(f"MODERATION | {action.upper()} | {moderator} -> {target} | {reason} | {guild}")

def log_error(error: Exception, context: str = ""):
    """
    Log errors with additional context.
    
    Args:
        error: The exception that occurred
        context: Additional context about where the error occurred
    """
    logger = logging.getLogger('error')
    error_msg = f"ERROR | {type(error).__name__}: {str(error)}"
    if context:
        error_msg += f" | Context: {context}"
    logger.error(error_msg, exc_info=True)
