"""
Moderation Cog
Contains all moderation-related slash commands like kick, ban, timeout, etc.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
from typing import Optional

from utils.permissions import has_moderation_permissions, has_higher_role

class ModerationCog(commands.Cog):
    """Moderation commands cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
    
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(
        member="The member to kick",
        reason="Reason for the kick"
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        """Kick a member from the server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
            
        # Check permissions
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to kick this member.", ephemeral=True)
            return
        
        if not has_higher_role(interaction.guild.me, member):
            await interaction.response.send_message("❌ I cannot kick this member due to role hierarchy.", ephemeral=True)
            return
        
        try:
            # Log the action
            self.logger.info(f"Kick command used by {interaction.user} on {member} in {interaction.guild.name if interaction.guild else 'Unknown Guild'}")
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="Member Kicked",
                description=f"**{member.display_name}** has been kicked from the server.",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Perform the kick
            await member.kick(reason=f"Kicked by {interaction.user}: {reason}")
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to kick member: {e}", ephemeral=True)
            self.logger.error(f"Failed to kick {member}: {e}")
    
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_messages="Number of days of messages to delete (0-7)"
    )
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided", delete_messages: Optional[int] = 0):
        """Ban a member from the server."""
        # Validate delete_messages parameter
        if delete_messages is not None and (delete_messages < 0 or delete_messages > 7):
            await interaction.response.send_message("❌ Delete messages must be between 0 and 7 days.", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
        
        # Check permissions
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to ban this member.", ephemeral=True)
            return
        
        if not has_higher_role(interaction.guild.me, member):
            await interaction.response.send_message("❌ I cannot ban this member due to role hierarchy.", ephemeral=True)
            return
        
        try:
            # Log the action
            self.logger.info(f"Ban command used by {interaction.user} on {member} in {interaction.guild.name}")
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="Member Banned",
                description=f"**{member.display_name}** has been banned from the server.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            if delete_messages > 0:
                embed.add_field(name="Messages Deleted", value=f"{delete_messages} days", inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Perform the ban
            await member.ban(reason=f"Banned by {interaction.user}: {reason}", delete_message_days=delete_messages or 0)
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to ban member: {e}", ephemeral=True)
            self.logger.error(f"Failed to ban {member}: {e}")
    
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration in minutes (max 40320 = 28 days)",
        reason="Reason for the timeout"
    )
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        """Timeout a member."""
        # Validate duration (max 28 days = 40320 minutes)
        if duration <= 0 or duration > 40320:
            await interaction.response.send_message("❌ Duration must be between 1 and 40320 minutes (28 days).", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
        
        # Check permissions
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to timeout this member.", ephemeral=True)
            return
        
        if not has_higher_role(interaction.guild.me, member):
            await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)
            return
        
        try:
            # Calculate timeout until time (timezone-aware)
            timeout_until = discord.utils.utcnow() + timedelta(minutes=duration)
            
            # Log the action
            self.logger.info(f"Timeout command used by {interaction.user} on {member} for {duration} minutes in {interaction.guild.name}")
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="Member Timed Out",
                description=f"**{member.display_name}** has been timed out.",
                color=discord.Color.yellow(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
            embed.add_field(name="Until", value=f"<t:{int(timeout_until.timestamp())}:f>", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Perform the timeout
            await member.timeout(timeout_until, reason=f"Timed out by {interaction.user}: {reason}")
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to timeout member: {e}", ephemeral=True)
            self.logger.error(f"Failed to timeout {member}: {e}")
    
    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.describe(
        member="The member to remove timeout from",
        reason="Reason for removing the timeout"
    )
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        """Remove timeout from a member."""
        # Check if member is actually timed out
        if member.timed_out_until is None:
            await interaction.response.send_message("❌ This member is not currently timed out.", ephemeral=True)
            return
        
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
        
        # Check permissions
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to remove timeout from this member.", ephemeral=True)
            return
        
        try:
            # Log the action
            self.logger.info(f"Untimeout command used by {interaction.user} on {member} in {interaction.guild.name}")
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="Timeout Removed",
                description=f"**{member.display_name}**'s timeout has been removed.",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Remove the timeout
            await member.timeout(None, reason=f"Timeout removed by {interaction.user}: {reason}")
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to remove timeout from this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)
            self.logger.error(f"Failed to remove timeout from {member}: {e}")
    
    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(
        user_id="The ID of the user to unban",
        reason="Reason for the unban"
    )
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = "No reason provided"):
        """Unban a user from the server."""
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used by server members.", ephemeral=True)
            return
            
        # Check permissions
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to unban members.", ephemeral=True)
            return
        
        try:
            # Convert user_id to int
            user_id = int(user_id)
            user = await self.bot.fetch_user(user_id)
            
            # Check if user is actually banned
            try:
                ban_entry = await interaction.guild.fetch_ban(user)
            except discord.NotFound:
                await interaction.response.send_message("❌ This user is not banned from this server.", ephemeral=True)
                return
            
            # Log the action
            self.logger.info(f"Unban command used by {interaction.user} for user {user_id} in {interaction.guild.name}")
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="User Unbanned",
                description=f"**{user.display_name}** has been unbanned from the server.",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            
            # Perform the unban
            await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user}: {reason}")
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID provided.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ User not found.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unban users.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)
            self.logger.error(f"Failed to unban user {user_id}: {e}")

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(ModerationCog(bot))
