"""
Command handling utilities for both slash and prefix commands.
"""
import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

def handle_command_error(func):
    """
    Decorator to handle command errors and responses properly for both slash and prefix commands.
    """
    async def wrapper(self, ctx, *args, **kwargs):
        try:
            # Delete message for prefix commands
            if not isinstance(ctx, discord.Interaction) and hasattr(ctx, 'message'):
                try:
                    await ctx.message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                except Exception as e:
                    logger.error(f"Error deleting command message: {e}")

            # Execute the command
            return await func(self, ctx, *args, **kwargs)

        except Exception as e:
            error_msg = f"❌ An error occurred: {str(e)}"
            try:
                if isinstance(ctx, discord.Interaction):
                    if not ctx.response.is_done():
                        await ctx.response.send_message(error_msg, ephemeral=True)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                else:
                    await ctx.send(error_msg, delete_after=5)
            except Exception as send_error:
                logger.error(f"Error sending error message: {send_error}")
            logger.error(f"Command error in {func.__name__}: {e}", exc_info=True)

    return wrapper

async def send_response(ctx, content=None, **kwargs):
    """
    Universal send method that works with both Context and Interaction objects.
    
    Args:
        ctx: Context or Interaction object
        content: Message content to send
        **kwargs: Additional message options (embed, file, etc.)
    """
    try:
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(content, **kwargs)
            else:
                await ctx.followup.send(content, **kwargs)
        else:
            return await ctx.send(content, **kwargs)
    except Exception as e:
        logger.error(f"Error in send_response: {e}")
        return None

def hybrid_cooldown(rate, per, bucket=commands.BucketType.user):
    """
    Apply cooldown to both slash and prefix versions of a command.
    
    Args:
        rate: Number of uses allowed
        per: Time period in seconds
        bucket: BucketType to track cooldown (default: per-user)
    """
    def decorator(func):
        if isinstance(func, commands.Command):
            func._buckets = commands.CooldownMapping.from_cooldown(rate, per, bucket)
        else:
            func.__commands_cooldown__ = commands.Cooldown(rate, per)
        return func
    return decorator
