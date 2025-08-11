# -*- coding: utf-8 -*-
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

    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # ---------- tiny builder for compact Dyno-like embeds ----------
    def _dyno_style_embed(self, verb_past: str, target: discord.abc.User, reason: str) -> discord.Embed:
        """
        Build a compact embed:
        - color: green
        - description: "**name** was <verb>.\n***Reason:*** <reason>"
        - footer will be added by caller (User ID only)
        """
        display = getattr(target, "display_name", getattr(target, "name", "User"))
        return discord.Embed(
            description=f"**{display}** was {verb_past}.\n***Reason:*** {reason}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

    # ==============================
    # Slash commands
    # ==============================

    # Kick
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to kick this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot kick this member due to role hierarchy.", ephemeral=True)

        # DM best-effort
        try:
            dm = discord.Embed(
                title=f"You were kicked from {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.kick(reason=f"Kicked by staff: {reason}")
            e = self._dyno_style_embed("kicked", member, reason)
            e.set_footer(text=f"User ID: {member.id}")
            await interaction.response.send_message(embed=e)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this member.", ephemeral=True)

    # Ban
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_messages="Number of days of messages to delete (0-7)"
    )
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided", delete_messages: Optional[int] = 0):
        if delete_messages is not None and (delete_messages < 0 or delete_messages > 7):
            return await interaction.response.send_message("❌ Delete messages must be between 0 and 7 days.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to ban this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot ban this member due to role hierarchy.", ephemeral=True)

        # DM best-effort
        try:
            dm = discord.Embed(
                title=f"You were banned from {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.ban(reason=f"Banned by staff: {reason}", delete_message_days=delete_messages or 0)
            e = self._dyno_style_embed("banned", member, reason)
            if delete_messages:
                e.description += f"\n***Messages Deleted:*** {delete_messages} day(s)"
            e.set_footer(text=f"User ID: {member.id}")
            await interaction.response.send_message(embed=e)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this member.", ephemeral=True)

    # Timeout
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="The member to timeout", duration="Duration in minutes (max 40320 = 28 days)", reason="Reason for the timeout")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        if duration <= 0 or duration > 40320:
            return await interaction.response.send_message("❌ Duration must be between 1 and 40320 minutes (28 days).", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to timeout this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)

        until = discord.utils.utcnow() + timedelta(minutes=duration)

        # DM best-effort
        try:
            dm = discord.Embed(
                title=f"You were timed out in {interaction.guild.name}",
                description=(
                    f"***Duration:*** {duration} minutes\n"
                    f"***Until:*** {discord.utils.format_dt(until, style='F')}\n"
                    f"***Reason:*** {reason}"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.timeout(until, reason=f"Timed out by staff: {reason}")
            e = self._dyno_style_embed("timed out", member, reason)
            # Put Until + Duration in the description for localization
            e.description += f"\n***Until:*** {discord.utils.format_dt(until, style='F')} • ***Duration:*** {duration}m"
            e.set_footer(text=f"User ID: {member.id}")
            await interaction.response.send_message(embed=e)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this member.", ephemeral=True)

    # Untimeout
    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.describe(member="The member to remove timeout from", reason="Reason for removing the timeout")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        if member.timed_out_until is None:
            return await interaction.response.send_message("❌ This member is not currently timed out.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to remove timeout from this member.", ephemeral=True)

        # DM best-effort
        try:
            dm = discord.Embed(
                title=f"Your timeout was removed in {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")
            e = self._dyno_style_embed("had their timeout removed", member, reason)
            e.set_footer(text=f"User ID: {member.id}")
            await interaction.response.send_message(embed=e)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to remove timeout from this member.", ephemeral=True)

    # Unban (slash)
    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user_id="The ID of the user to unban", reason="Reason for the unban")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = "No reason provided"):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used by server members.", ephemeral=True)
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("❌ You don't have permission to unban members.", ephemeral=True)

        try:
            uid = int(user_id)
            user = await self.bot.fetch_user(uid)
            try:
                await interaction.guild.fetch_ban(user)
            except discord.NotFound:
                return await interaction.response.send_message("❌ This user is not banned from this server.", ephemeral=True)

            await interaction.guild.unban(user, reason=f"Unbanned by staff: {reason}")
            e = self._dyno_style_embed("unbanned", user, reason)
            e.set_footer(text=f"User ID: {user.id}")
            await interaction.response.send_message(embed=e)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID provided.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ User not found.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unban users.", ephemeral=True)

    # ==============================
    # Prefix commands (message)
    # ==============================

    @commands.command(name="kick")
    async def prefix_kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        if not has_moderation_permissions(ctx.author, member):
            return await ctx.send("❌ You don't have permission to kick this member.", delete_after=5)
        if not has_higher_role(ctx.guild.me, member):
            return await ctx.send("❌ I cannot kick this member due to role hierarchy.", delete_after=5)

        try:
            dm = discord.Embed(
                title=f"You were kicked from {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.kick(reason=f"Kicked by staff: {reason}")
            e = self._dyno_style_embed("kicked", member, reason)
            e.set_footer(text=f"User ID: {member.id}")
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to kick this member.", delete_after=5)

    @commands.command(name="ban")
    async def prefix_ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        if not has_moderation_permissions(ctx.author, member):
            return await ctx.send("❌ You don't have permission to ban this member.", delete_after=5)
        if not has_higher_role(ctx.guild.me, member):
            return await ctx.send("❌ I cannot ban this member due to role hierarchy.", delete_after=5)

        try:
            dm = discord.Embed(
                title=f"You were banned from {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.ban(reason=f"Banned by staff: {reason}")
            e = self._dyno_style_embed("banned", member, reason)
            e.set_footer(text=f"User ID: {member.id}")
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban this member.", delete_after=5)

    @commands.command(name="timeout")
    async def prefix_timeout(self, ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        if minutes <= 0 or minutes > 40320:
            return await ctx.send("❌ Duration must be between 1 and 40320 minutes (28 days).", delete_after=5)
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        if not has_moderation_permissions(ctx.author, member):
            return await ctx.send("❌ You don't have permission to timeout this member.", delete_after=5)
        if not has_higher_role(ctx.guild.me, member):
            return await ctx.send("❌ I cannot timeout this member due to role hierarchy.", delete_after=5)

        until = discord.utils.utcnow() + timedelta(minutes=minutes)

        try:
            dm = discord.Embed(
                title=f"You were timed out in {ctx.guild.name}",
                description=(
                    f"***Duration:*** {minutes} minutes\n"
                    f"***Until:*** {discord.utils.format_dt(until, style='F')}\n"
                    f"***Reason:*** {reason}"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.timeout(until, reason=f"Timed out by staff: {reason}")
            e = self._dyno_style_embed("timed out", member, reason)
            e.description += f"\n***Until:*** {discord.utils.format_dt(until, style='F')} • ***Duration:*** {minutes}m"
            e.set_footer(text=f"User ID: {member.id}")
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to timeout this member.", delete_after=5)

    @commands.command(name="untimeout")
    async def prefix_untimeout(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        if not has_moderation_permissions(ctx.author, member):
            return await ctx.send("❌ You don't have permission to remove timeout from this member.", delete_after=5)

        try:
            dm = discord.Embed(
                title=f"Your timeout was removed in {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")
            e = self._dyno_style_embed("had their timeout removed", member, reason)
            e.set_footer(text=f"User ID: {member.id}")
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to remove timeout from this member.", delete_after=5)

    @commands.command(name="unban")
    async def prefix_unban(self, ctx, user_id: int, *, reason: str = "No reason provided"):
        await self.delete_command_message(ctx)
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.send("❌ You don't have permission to unban members.", delete_after=5)

        try:
            user = await self.bot.fetch_user(user_id)
            try:
                await ctx.guild.fetch_ban(user)
            except discord.NotFound:
                return await ctx.send("❌ That user is not banned from this server.", delete_after=5)

            await ctx.guild.unban(user, reason=f"Unbanned by staff: {reason}")
            e = self._dyno_style_embed("unbanned", user, reason)
            e.set_footer(text=f"User ID: {user.id}")
            await ctx.send(embed=e)
        except discord.NotFound:
            await ctx.send("❌ User not found.", delete_after=5)
        except discord.HTTPException as err:
            await ctx.send(f"❌ Failed to unban user: {err}", delete_after=5)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(ModerationCog(bot))