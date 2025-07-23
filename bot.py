"""
Discord Bot Main Class
Contains the main bot class with event handlers and cog loading.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands

# Import cogs
from cogs.moderation import ModerationCog
from cogs.utility import UtilityCog
from cogs.admin import AdminCog

class DiscordBot(commands.Bot):
    """Main Discord bot class with slash command support."""
    
    def __init__(self):
        """Initialize the bot with necessary intents and settings."""
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.moderation = True
        
        # Initialize bot
        super().__init__(
            command_prefix='!',  # Prefix commands with auto-delete
            intents=intents,
            help_command=None,
            case_insensitive=True
        )
        
        self.logger = logging.getLogger(__name__)
    
    async def setup_hook(self):
        """Called when the bot is starting up. Load cogs and sync commands."""
        self.logger.info("Bot setup hook called")
        
        # Add cogs
        await self.add_cog(ModerationCog(self))
        await self.add_cog(UtilityCog(self))
        await self.add_cog(AdminCog(self))
        
        self.logger.info("All cogs loaded successfully")
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            self.logger.error(f"Failed to sync slash commands: {e}")
    
    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        if self.user:
            self.logger.info(f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"Connected to {len(self.guilds)} guilds")
        
        # Set bot activity
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="for rule violations"
        )
        await self.change_presence(activity=activity, status=discord.Status.online)
    
    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild."""
        self.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Try to sync commands for this guild
        try:
            await self.tree.sync(guild=guild)
            self.logger.info(f"Synced commands for guild: {guild.name}")
        except Exception as e:
            self.logger.error(f"Failed to sync commands for {guild.name}: {e}")
    
    async def on_guild_remove(self, guild):
        """Called when the bot leaves a guild."""
        self.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
    
    async def on_command_error(self, ctx, error):
        """Handle command errors for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        
        self.logger.error(f"Command error in {ctx.command}: {error}")
        
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the necessary permissions to execute this command.")
        else:
            await ctx.send("❌ An error occurred while executing the command.")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle slash command errors."""
        self.logger.error(f"Slash command error: {error}")
        
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message("❌ I don't have the necessary permissions to execute this command.", ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred while executing the command.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred while executing the command.", ephemeral=True)
