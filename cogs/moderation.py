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
        # simple in-memory case counter (resets on restart)
        self._case_counter = 0

    def _next_case(self) -> int:
        self._case_counter += 1
        return self._case_counter
    
    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # ---------- Helpers for compact Dyno-style embeds ----------
    def _dyno_style_embed(self, verb_past: str, target: discord.abc.User, reason: str):
        """
        Build the compact, Dyno-like embed body:
        - color: green (your main color)
        - description: "**name** was <verb>.\n***Reason:*** <reason>"
        - returns (embed, case_no) so caller can set footer
        """
        case_no = self._next_case()
        display = getattr(target, "display_name", getattr(target, "name", "User"))
        embed = discord.Embed(
            description=f"**{display}** was {verb_past}.\n***Reason:*** {reason}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        return embed, case_no

    def _meta_footer(self, case_no: int, user_id: int, extras: Optional[list[str]] = None) -> str:
        bits = [f"Case #{case_no}", f"User ID: {user_id}"]
        if extras:
            bits.extend(extras)
        return " • ".join(bits)

    # --------------------
    # KICK (DM + hide mod)
    # --------------------
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

        # Try to DM first (best-effort)
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
        except Exception:
            pass
        
        try:
            # Perform the kick
            await member.kick(reason=f"Kicked by staff: {reason}")
            # Public confirmation (Dyno style)
            embed, case_no = self._dyno_style_embed("kicked", member, reason)
            embed.set_footer(text=self._meta_footer(case_no, member.id))
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to kick member: {e}", ephemeral=True)
            self.logger.error(f"Failed to kick {member}: {e}")

    # --------------------
    # BAN (DM + hide mod)
    # --------------------
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_messages="Number of days of messages to delete (0-7)"
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
        delete_messages: Optional[int] = 0
    ):
        """Ban a member; DM them the reason; hide the moderator in the public message."""
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
        
        # Try to DM first (best-effort)
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
        except Exception:
            pass
        
        try:
            # Perform the ban
            await member.ban(
                reason=f"Banned by staff: {reason}",
                delete_message_days=delete_messages or 0
            )
            # Public confirmation (Dyno style)
            embed, case_no = self._dyno_style_embed("banned", member, reason)
            extras = [f"Messages Deleted: {delete_messages} day(s)"] if delete_messages else None
            embed.set_footer(text=self._meta_footer(case_no, member.id, extras))
            await interaction.response.send_message(embed=embed)  # public
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to ban member: {e}", ephemeral=True)
            self.logger.error(f"Failed to ban {member}: {e}")

    # --------------------
    # TIMEOUT (DM + hide mod)
    # --------------------
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration in minutes (max 40320 = 28 days)",
        reason="Reason for the timeout"
    )
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        """Timeout a member."""
        if duration <= 0 or duration > 40320:
            await interaction.response.send_message("❌ Duration must be between 1 and 40320 minutes (28 days).", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
        
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to timeout this member.", ephemeral=True)
            return
        
        if not has_higher_role(interaction.guild.me, member):
            await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)
            return
        
        timeout_until = discord.utils.utcnow() + timedelta(minutes=duration)

        # Try to DM first (best-effort)
        try:
            dm_embed = discord.Embed(
                title=f"You were timed out in {interaction.guild.name}",
                description=(
                    f"***Duration:*** {duration} minutes\n"
                    f"***Until:*** <t:{int(timeout_until.timestamp())}:F>\n"
                    f"***Reason:*** {reason}"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass
        
        try:
            # Perform the timeout
            await member.timeout(timeout_until, reason=f"Timed out by staff: {reason}")
            # Public confirmation (Dyno style)
            until_str = discord.utils.format_dt(timeout_until, style="f")
            embed, case_no = self._dyno_style_embed("timed out", member, reason)
            embed.set_footer(text=self._meta_footer(case_no, member.id, [f"Until: {until_str}", f"Duration: {duration}m"]))
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to timeout member: {e}", ephemeral=True)
            self.logger.error(f"Failed to timeout {member}: {e}")

    # --------------------
    # UNTIMEOUT (DM + hide mod)
    # --------------------
    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.describe(
        member="The member to remove timeout from",
        reason="Reason for removing the timeout"
    )
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        """Remove timeout from a member."""
        if member.timed_out_until is None:
            await interaction.response.send_message("❌ This member is not currently timed out.", ephemeral=True)
            return
        
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return
        
        if not has_moderation_permissions(interaction.user, member):
            await interaction.response.send_message("❌ You don't have permission to remove timeout from this member.", ephemeral=True)
            return
        
        # Try to DM (best-effort)
        try:
            dm_embed = discord.Embed(
                title=f"Your timeout was removed in {interaction.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass

        try:
            # Remove the timeout
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")
            # Public confirmation (Dyno style)
            embed, case_no = self._dyno_style_embed("had their timeout removed", member, reason)
            embed.set_footer(text=self._meta_footer(case_no, member.id))
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to remove timeout from this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)
            self.logger.error(f"Failed to remove timeout from {member}: {e}")

    # --------------------
    # UNBAN (slash)
    # --------------------
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
            
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to unban members.", ephemeral=True)
            return
        
        try:
            user_id_int = int(user_id)
            user = await self.bot.fetch_user(user_id_int)
            try:
                await interaction.guild.fetch_ban(user)
            except discord.NotFound:
                await interaction.response.send_message("❌ This user is not banned from this server.", ephemeral=True)
                return
            
            # Do the unban
            await interaction.guild.unban(user, reason=f"Unbanned by staff: {reason}")

            # Public confirmation (Dyno style)
            embed, case_no = self._dyno_style_embed("unbanned", user, reason)
            embed.set_footer(text=self._meta_footer(case_no, user.id))
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

    # --------------------
    # Prefix commands (auto-delete invoking message)
    # --------------------
    @commands.command(name="kick")
    async def prefix_kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Prefix version of kick command."""
        await self.delete_command_message(ctx)
        
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
            
        if not has_moderation_permissions(ctx.author, member):
            await ctx.send("❌ You don't have permission to kick this member.", delete_after=5)
            return
        
        if not has_higher_role(ctx.guild.me, member):
            await ctx.send("❌ I cannot kick this member due to role hierarchy.", delete_after=5)
            return
        
        # DM best-effort
        try:
            dm_embed = discord.Embed(
                title=f"You were kicked from {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await member.kick(reason=f"Kicked by staff: {reason}")
            embed, case_no = self._dyno_style_embed("kicked", member, reason)
            embed.set_footer(text=self._meta_footer(case_no, member.id))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to kick this member.", delete_after=5)

    @commands.command(name="ban")
    async def prefix_ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Prefix version of ban: DM first, hide moderator in public embed."""
        await self.delete_command_message(ctx)
        
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
            
        if not has_moderation_permissions(ctx.author, member):
            await ctx.send("❌ You don't have permission to ban this member.", delete_after=5)
            return
        
        if not has_higher_role(ctx.guild.me, member):
            await ctx.send("❌ I cannot ban this member due to role hierarchy.", delete_after=5)
            return

        try:
            dm_embed = discord.Embed(
                title=f"You were banned from {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await member.ban(reason=f"Banned by staff: {reason}")
            embed, case_no = self._dyno_style_embed("banned", member, reason)
            embed.set_footer(text=self._meta_footer(case_no, member.id))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban this member.", delete_after=5)

    @commands.command(name="timeout")
    async def prefix_timeout(self, ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
        """Prefix version of timeout: DM first, hide moderator in public embed."""
        await self.delete_command_message(ctx)

        if minutes <= 0 or minutes > 40320:
            await ctx.send("❌ Duration must be between 1 and 40320 minutes (28 days).", delete_after=5)
            return

        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return

        if not has_moderation_permissions(ctx.author, member):
            await ctx.send("❌ You don't have permission to timeout this member.", delete_after=5)
            return

        if not has_higher_role(ctx.guild.me, member):
            await ctx.send("❌ I cannot timeout this member due to role hierarchy.", delete_after=5)
            return

        until = discord.utils.utcnow() + timedelta(minutes=minutes)

        try:
            dm_embed = discord.Embed(
                title=f"You were timed out in {ctx.guild.name}",
                description=(
                    f"***Duration:*** {minutes} minutes\n"
                    f"***Until:*** <t:{int(until.timestamp())}:F>\n"
                    f"***Reason:*** {reason}"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await member.timeout(until, reason=f"Timed out by staff: {reason}")
            until_str = discord.utils.format_dt(until, style="f")
            e, case_no = self._dyno_style_embed("timed out", member, reason)
            e.set_footer(text=self._meta_footer(case_no, member.id, [f"Until: {until_str}", f"Duration: {minutes}m"]))
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to timeout this member.", delete_after=5)

    @commands.command(name="untimeout")
    async def prefix_untimeout(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Prefix version of untimeout: DM best-effort, hide moderator."""
        await self.delete_command_message(ctx)

        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return

        if not has_moderation_permissions(ctx.author, member):
            await ctx.send("❌ You don't have permission to remove timeout from this member.", delete_after=5)
            return

        try:
            dm_embed = discord.Embed(
                title=f"Your timeout was removed in {ctx.guild.name}",
                description=f"***Reason:*** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")
            e, case_no = self._dyno_style_embed("had their timeout removed", member, reason)
            e.set_footer(text=self._meta_footer(case_no, member.id))
            await ctx.send(embed=e)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to remove timeout from this member.", delete_after=5)

    @commands.command(name="unban")
    async def prefix_unban(self, ctx, user_id: int, *, reason: str = "No reason provided"):
        """Prefix version of unban: auto-delete command message and unban by user ID."""
        await self.delete_command_message(ctx)

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return

        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("❌ You don't have permission to unban members.", delete_after=5)
            return

        try:
            user = await self.bot.fetch_user(user_id)

            # Ensure they are actually banned
            try:
                await ctx.guild.fetch_ban(user)
            except discord.NotFound:
                await ctx.send("❌ That user is not banned from this server.", delete_after=5)
                return

            # Unban
            await ctx.guild.unban(user, reason=f"Unbanned by staff: {reason}")

            # Public confirmation (Dyno style)
            embed, case_no = self._dyno_style_embed("unbanned", user, reason)
            embed.set_footer(text=self._meta_footer(case_no, user.id))
            await ctx.send(embed=embed)

        except discord.NotFound:
            await ctx.send("❌ User not found.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to unban user: {e}", delete_after=5)
        except Exception:
            await ctx.send("❌ Something went wrong while trying to unban.", delete_after=5)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(ModerationCog(bot))