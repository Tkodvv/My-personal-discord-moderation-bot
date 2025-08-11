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
        self._case_counter = 0

    def _next_case(self) -> int:
        self._case_counter += 1
        return self._case_counter

    def _dyno_style_embed(self, verb_past: str, target: discord.abc.User, reason: str, footer_note: Optional[str] = None) -> discord.Embed:
        """Build compact Dyno-like embed."""
        case_no = self._next_case()
        desc_lines = [
            f"**{getattr(target, 'display_name', getattr(target, 'name', 'User'))}** was {verb_past}.",
            f"***Reason:*** {reason}"
        ]
        embed = discord.Embed(
            description="\n".join(desc_lines),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        try:
            icon = target.display_avatar.url
        except Exception:
            icon = None
        embed.set_author(name="Moderation", icon_url=icon or discord.Embed.Empty)

        footer_bits = [f"Case #{case_no}", f"User ID: {getattr(target, 'id', 'N/A')}"]
        if footer_note:
            footer_bits.append(footer_note)
        embed.set_footer(text=" • ".join(footer_bits))
        return embed

    # ---------- Kick ----------
    @app_commands.command(name="kick", description="Kick a member from the server")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to kick this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot kick this member due to role hierarchy.", ephemeral=True)

        try:
            dm_embed = discord.Embed(
                title=f"You were kicked from {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
        except:
            pass

        try:
            await member.kick(reason=f"Kicked by staff: {reason}")
            embed = self._dyno_style_embed("kicked", member, reason)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this member.", ephemeral=True)

    # ---------- Ban ----------
    @app_commands.command(name="ban", description="Ban a member from the server")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided", delete_messages: Optional[int] = 0):
        if delete_messages < 0 or delete_messages > 7:
            return await interaction.response.send_message("❌ Delete messages must be 0–7 days.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to ban this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot ban this member due to role hierarchy.", ephemeral=True)

        try:
            dm_embed = discord.Embed(
                title=f"You were banned from {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
        except:
            pass

        try:
            await member.ban(reason=f"Banned by staff: {reason}", delete_message_days=delete_messages or 0)
            note = f"Messages Deleted: {delete_messages} day(s)" if delete_messages else None
            embed = self._dyno_style_embed("banned", member, reason, footer_note=note)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this member.", ephemeral=True)

    # ---------- Timeout ----------
    @app_commands.command(name="timeout", description="Timeout a member")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        if duration <= 0 or duration > 40320:
            return await interaction.response.send_message("❌ Duration must be between 1 and 40320 minutes.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to timeout this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)

        timeout_until = discord.utils.utcnow() + timedelta(minutes=duration)
        try:
            dm_embed = discord.Embed(
                title=f"You were timed out in {interaction.guild.name}",
                description=f"***Duration:*** {duration} minutes\n***Until:*** <t:{int(timeout_until.timestamp())}:F>\n***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
        except:
            pass

        try:
            await member.timeout(timeout_until, reason=f"Timed out by staff: {reason}")
            note = f"Until: {discord.utils.format_dt(timeout_until, style='f')} · Duration: {duration}m"
            embed = self._dyno_style_embed("timed out", member, reason, footer_note=note)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this member.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))