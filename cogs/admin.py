"""
Admin Cog
Contains administrative commands like say, announce, clear, and prefix management.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional

class AdminCog(commands.Cog):
    """Administrative commands cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        # Store deleted messages for snipe command
        self.deleted_messages = {}
    
    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Store deleted messages for snipe command."""
        if message.author.bot:
            return
        
        self.deleted_messages[message.channel.id] = {
            'content': message.content,
            'author': message.author,
            'created_at': message.created_at,
            'deleted_at': datetime.utcnow()
        }
    
    @app_commands.command(name="say", description="Make the bot say something")
    @app_commands.describe(message="The message to send")
    async def say(self, interaction: discord.Interaction, message: str):
        """Make the bot say a message."""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        # Log the action
        self.logger.info(f"Say command used by {interaction.user} in {interaction.guild.name}")
        
        # Send the message
        await interaction.response.send_message(message)
    
    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(
        title="Title of the announcement",
        message="The announcement message",
        channel="Channel to send the announcement to (optional)"
    )
    async def announce(self, interaction: discord.Interaction, title: str, message: str, channel: Optional[discord.TextChannel] = None):
        """Send an announcement with embed formatting."""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        
        # Create announcement embed
        embed = discord.Embed(
            title=f"📢 {title}",
            description=message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Announced by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        # Log the action
        self.logger.info(f"Announce command used by {interaction.user} in {interaction.guild.name}")
        
        try:
            if isinstance(target_channel, discord.TextChannel):
                await target_channel.send(embed=embed)
                if target_channel != interaction.channel:
                    await interaction.response.send_message(f"✅ Announcement sent to {target_channel.mention}", ephemeral=True)
                else:
                    await interaction.response.send_message("✅ Announcement sent!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send announcement: {e}", ephemeral=True)
    
    @app_commands.command(name="clear", description="Clear messages from the channel")
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        user="Only delete messages from this user (optional)"
    )
    async def clear(self, interaction: discord.Interaction, amount: int, user: Optional[discord.Member] = None):
        """Clear messages from the channel."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used by server members.", ephemeral=True)
            return
            
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        # Validate amount
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
            return
        
        # Defer response as this might take time
        await interaction.response.defer(ephemeral=True)
        
        try:
            if user:
                # Delete messages from specific user
                def check(message):
                    return message.author == user
                
                deleted = await interaction.channel.purge(limit=amount * 2, check=check)
                deleted_count = len(deleted)
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages from {user.mention}", ephemeral=True)
            else:
                # Delete all messages
                deleted = await interaction.channel.purge(limit=amount)
                deleted_count = len(deleted)
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages", ephemeral=True)
            
            # Log the action
            self.logger.info(f"Clear command used by {interaction.user} - deleted {deleted_count} messages in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to delete messages: {e}", ephemeral=True)
    
    @app_commands.command(name="snipe", description="Show the last deleted message in this channel")
    async def snipe(self, interaction: discord.Interaction):
        """Show the last deleted message in the current channel."""
        channel_id = interaction.channel.id
        
        if channel_id not in self.deleted_messages:
            await interaction.response.send_message("❌ No recently deleted messages found in this channel.", ephemeral=True)
            return
        
        deleted_msg = self.deleted_messages[channel_id]
        
        # Create embed
        embed = discord.Embed(
            title="🎯 Sniped Message",
            description=deleted_msg['content'] or "*No content*",
            color=discord.Color.orange(),
            timestamp=deleted_msg['created_at']
        )
        embed.set_author(
            name=deleted_msg['author'].display_name,
            icon_url=deleted_msg['author'].display_avatar.url
        )
        embed.set_footer(text="Message deleted")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="setprefix", description="Change the bot's command prefix")
    @app_commands.describe(prefix="New prefix for the bot (max 5 characters)")
    async def setprefix(self, interaction: discord.Interaction, prefix: str):
        """Change the bot's command prefix."""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to change the prefix.", ephemeral=True)
            return
        
        # Validate prefix
        if len(prefix) > 5:
            await interaction.response.send_message("❌ Prefix must be 5 characters or less.", ephemeral=True)
            return
        
        # Update bot prefix
        self.bot.command_prefix = prefix
        
        # Create confirmation embed
        embed = discord.Embed(
            title="✅ Prefix Changed",
            description=f"Bot prefix has been changed to `{prefix}`",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Changed by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        # Log the action
        self.logger.info(f"Prefix changed to '{prefix}' by {interaction.user} in {interaction.guild.name}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="dm", description="Send a direct message to a user")
    @app_commands.describe(
        user="The user to send a DM to",
        message="The message to send"
    )
    async def dm_user(self, interaction: discord.Interaction, user: discord.User, *, message: str):
        """Send a direct message to a user."""
        # Check permissions
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            # Create embed for the DM
            embed = discord.Embed(
                title=f"Message from {interaction.guild.name}",
                description=message,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"Sent by {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url
            )
            embed.set_footer(text=f"From: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            
            # Send the DM
            await user.send(embed=embed)
            
            # Confirm to the sender
            await interaction.response.send_message(f"✅ Direct message sent to {user.display_name}!", ephemeral=True)
            
            # Log the action
            self.logger.info(f"DM sent to {user} by {interaction.user} in {interaction.guild.name}: {message}")
            
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ Could not send DM to {user.display_name}. They may have DMs disabled or blocked the bot.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to send DM: {e}", ephemeral=True)
            self.logger.error(f"Failed to send DM to {user}: {e}")
    
    # Prefix command versions (auto-delete)
    @commands.command(name="say")
    async def prefix_say(self, ctx, *, message):
        """Prefix version of say command."""
        await self.delete_command_message(ctx)
        
        if not isinstance(ctx.author, discord.Member):
            return
            
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=5)
            return
        
        await ctx.send(message)
    
    @commands.command(name="clear")
    async def prefix_clear(self, ctx, amount: int, member: Optional[discord.Member] = None):
        """Prefix version of clear command."""
        await self.delete_command_message(ctx)
        
        if not isinstance(ctx.author, discord.Member):
            return
            
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=5)
            return
        
        if amount < 1 or amount > 100:
            await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
            return
        
        try:
            if member:
                def check(msg):
                    return msg.author == member
                deleted = await ctx.channel.purge(limit=amount * 2, check=check)
            else:
                deleted = await ctx.channel.purge(limit=amount)
            
            confirmation = await ctx.send(f"✅ Deleted {len(deleted)} messages")
            await confirmation.delete(delay=3)
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)
    
    @commands.command(name="snipe")
    async def prefix_snipe(self, ctx):
        """Prefix version of snipe command."""
        await self.delete_command_message(ctx)
        
        channel_id = ctx.channel.id
        if channel_id not in self.deleted_messages:
            await ctx.send("❌ No recently deleted messages found.", delete_after=5)
            return
        
        deleted_msg = self.deleted_messages[channel_id]
        embed = discord.Embed(
            title="🎯 Sniped Message",
            description=deleted_msg['content'] or "*No content*",
            color=discord.Color.orange(),
            timestamp=deleted_msg['created_at']
        )
        embed.set_author(
            name=deleted_msg['author'].display_name,
            icon_url=deleted_msg['author'].display_avatar.url
        )
        await ctx.send(embed=embed)
    
    @commands.command(name="dm")
    async def prefix_dm(self, ctx, user: discord.User, *, message):
        """Prefix version of dm command."""
        await self.delete_command_message(ctx)
        
        if not isinstance(ctx.author, discord.Member):
            return
            
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=5)
            return
        
        try:
            # Create embed for the DM
            embed = discord.Embed(
                title=f"Message from {ctx.guild.name}",
                description=message,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"Sent by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            embed.set_footer(text=f"From: {ctx.guild.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            
            # Send the DM
            await user.send(embed=embed)
            
            # Confirm to the sender
            confirmation = await ctx.send(f"✅ Direct message sent to {user.display_name}!")
            await confirmation.delete(delay=3)
            
            # Log the action
            self.logger.info(f"DM sent to {user} by {ctx.author} in {ctx.guild.name}: {message}")
            
        except discord.Forbidden:
            await ctx.send(f"❌ Could not send DM to {user.display_name}. They may have DMs disabled or blocked the bot.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to send DM: {e}", delete_after=5)
            self.logger.error(f"Failed to send DM to {user}: {e}")

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(AdminCog(bot))