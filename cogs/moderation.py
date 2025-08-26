# -*- coding: utf-8 -*-
"""
Moderation Cog
Contains all moderation-related slash commands like kick, ban, timeout, etc.
"""

import logging
import re
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
from typing import Optional
from utils.permissions import mod_check

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

    # ---------- regex helpers ----------
    def _invite_regex(self):
        # discord.gg/xxxx, discord.com/invite/xxxx, discordapp.com/invite/xxxx
        return re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+", re.IGNORECASE)

    def _url_regex(self):
        # simple URL matcher (http/https + domain)
        return re.compile(
            r"https?://[^\s/$.?#].[^\s]*",
            re.IGNORECASE
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
    @app_commands.command(name="ban", description="Ban a member or user from the server")
    @app_commands.describe(
        target="The member/user to ban (mention, ID, or username)",
        reason="Reason for the ban",
        delete_messages="Number of days of messages to delete (0-7)"
    )
    async def ban(self, interaction: discord.Interaction, target: str, reason: Optional[str] = "No reason provided", delete_messages: Optional[int] = 0):
        if delete_messages is not None and (delete_messages < 0 or delete_messages > 7):
            return await interaction.response.send_message("❌ Delete messages must be between 0 and 7 days.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        
        # Try to resolve the target (member, user ID, or fetch user)
        member = None
        user = None
        user_id = None
        
        # First, try to convert target to member if they're in the server
        try:
            # Try to get member by mention or ID
            if target.startswith('<@') and target.endswith('>'):
                user_id = int(target.strip('<@!>'))
            elif target.isdigit():
                user_id = int(target)
            else:
                # Try to find member by username/display name
                for m in interaction.guild.members:
                    if m.name.lower() == target.lower() or m.display_name.lower() == target.lower():
                        member = m
                        break
            
            if user_id and not member:
                member = interaction.guild.get_member(user_id)
            
        except ValueError:
            pass
        
        # If we found a member, do permission checks
        if member:
            if not has_moderation_permissions(interaction.user, member):
                return await interaction.response.send_message("❌ You don't have permission to ban this member.", ephemeral=True)
            if not has_higher_role(interaction.guild.me, member):
                return await interaction.response.send_message("❌ I cannot ban this member due to role hierarchy.", ephemeral=True)
            user = member
        else:
            # User not in server, try to fetch user object
            if not user_id:
                return await interaction.response.send_message("❌ Could not find that user. Please provide a valid user ID, mention, or username of someone in the server.", ephemeral=True)
            
            # Check if user has ban permissions for hackbans
            if not interaction.user.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ You need ban permissions to ban users not in the server.", ephemeral=True)
            
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return await interaction.response.send_message("❌ User not found.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.response.send_message("❌ Failed to fetch user information.", ephemeral=True)

        # Check if user is already banned
        try:
            ban_entry = await interaction.guild.fetch_ban(user)
            return await interaction.response.send_message(f"❌ {user.mention} is already banned.", ephemeral=True)
        except discord.NotFound:
            pass  # User is not banned, continue
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to check bans.", ephemeral=True)

        # Try to DM the user (best effort)
        if member:  # Only try to DM if they're in the server
            try:
                dm = discord.Embed(
                    title=f"You were banned from {interaction.guild.name}",
                    description=f"***Reason:*** {reason}",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                if interaction.guild.icon:
                    dm.set_thumbnail(url=interaction.guild.icon.url)
                await user.send(embed=dm)
            except Exception:
                pass

        try:
            await interaction.guild.ban(user, reason=f"Banned by {interaction.user}: {reason}", delete_message_days=delete_messages or 0)
            
            # Create success embed
            e = self._dyno_style_embed("banned", user, reason)
            if delete_messages:
                e.description += f"\n***Messages Deleted:*** {delete_messages} day(s)"
            e.set_footer(text=f"User ID: {user.id}")
            await interaction.response.send_message(embed=e)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this user.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)

    # Tempban
    @app_commands.command(name="tempban", description="Temporarily ban a member or user from the server")
    @app_commands.describe(
        target="The member/user to temporarily ban (mention, ID, or username)",
        duration="Duration (e.g., 1h, 30m, 1d, 2w)",
        reason="Reason for the temporary ban",
        delete_messages="Number of days of messages to delete (0-7)"
    )
    async def tempban(self, interaction: discord.Interaction, target: str, duration: str, reason: Optional[str] = "No reason provided", delete_messages: Optional[int] = 0):
        if delete_messages is not None and (delete_messages < 0 or delete_messages > 7):
            return await interaction.response.send_message("❌ Delete messages must be between 0 and 7 days.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        
        # Parse duration
        ban_duration = self._parse_duration(duration)
        if not ban_duration:
            return await interaction.response.send_message("❌ Invalid duration format. Use formats like: 1h, 30m, 1d, 2w", ephemeral=True)
        
        # Try to resolve the target (member, user ID, or fetch user)
        member = None
        user = None
        user_id = None
        
        # First, try to convert target to member if they're in the server
        try:
            # Try to get member by mention or ID
            if target.startswith('<@') and target.endswith('>'):
                user_id = int(target.strip('<@!>'))
            elif target.isdigit():
                user_id = int(target)
            else:
                # Try to find member by username/display name
                for m in interaction.guild.members:
                    if m.name.lower() == target.lower() or m.display_name.lower() == target.lower():
                        member = m
                        break
            
            if user_id and not member:
                member = interaction.guild.get_member(user_id)
            
        except ValueError:
            pass
        
        # If we found a member, do permission checks
        if member:
            if not has_moderation_permissions(interaction.user, member):
                return await interaction.response.send_message("❌ You don't have permission to ban this member.", ephemeral=True)
            if not has_higher_role(interaction.guild.me, member):
                return await interaction.response.send_message("❌ I cannot ban this member due to role hierarchy.", ephemeral=True)
            user = member
        else:
            # User not in server, try to fetch user object
            if not user_id:
                return await interaction.response.send_message("❌ Could not find that user. Please provide a valid user ID, mention, or username of someone in the server.", ephemeral=True)
            
            # Check if user has ban permissions for hackbans
            if not interaction.user.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ You need ban permissions to ban users not in the server.", ephemeral=True)
            
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return await interaction.response.send_message("❌ User not found.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.response.send_message("❌ Failed to fetch user information.", ephemeral=True)

        # Check if user is already banned
        try:
            ban_entry = await interaction.guild.fetch_ban(user)
            return await interaction.response.send_message(f"❌ {user.mention} is already banned.", ephemeral=True)
        except discord.NotFound:
            pass  # User is not banned, continue
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to check bans.", ephemeral=True)

        # Try to DM the user (best effort)
        if member:  # Only try to DM if they're in the server
            try:
                unban_time = discord.utils.utcnow() + ban_duration
                dm = discord.Embed(
                    title=f"You were temporarily banned from {interaction.guild.name}",
                    description=f"***Reason:*** {reason}\n***Duration:*** {duration}\n***Unban Time:*** <t:{int(unban_time.timestamp())}:F>",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                if interaction.guild.icon:
                    dm.set_thumbnail(url=interaction.guild.icon.url)
                await user.send(embed=dm)
            except Exception:
                pass

        try:
            await interaction.guild.ban(user, reason=f"Tempban by {interaction.user}: {reason} (Duration: {duration})", delete_message_days=delete_messages or 0)
            
            # Schedule unban
            unban_time = discord.utils.utcnow() + ban_duration
            self.bot.loop.create_task(self._schedule_unban(interaction.guild, user, ban_duration))
            
            # Create success embed
            e = self._dyno_style_embed("temporarily banned", user, reason)
            e.description += f"\n***Duration:*** {duration}\n***Unban Time:*** <t:{int(unban_time.timestamp())}:R>"
            if delete_messages:
                e.description += f"\n***Messages Deleted:*** {delete_messages} day(s)"
            e.set_footer(text=f"User ID: {user.id}")
            await interaction.response.send_message(embed=e)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this user.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)

    def _parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse duration string like '1h', '30m', '1d', '2w' into timedelta."""
        import re
        
        # Match number followed by unit
        match = re.match(r'^(\d+)([smhdw])$', duration_str.lower())
        if not match:
            return None
        
        amount, unit = match.groups()
        amount = int(amount)
        
        if unit == 's':
            return timedelta(seconds=amount)
        elif unit == 'm':
            return timedelta(minutes=amount)
        elif unit == 'h':
            return timedelta(hours=amount)
        elif unit == 'd':
            return timedelta(days=amount)
        elif unit == 'w':
            return timedelta(weeks=amount)
        
        return None
    
    async def _schedule_unban(self, guild: discord.Guild, user: discord.User, duration: timedelta):
        """Schedule an unban after the specified duration."""
        await asyncio.sleep(duration.total_seconds())
        
        try:
            # Check if user is still banned
            await guild.fetch_ban(user)
            # If we get here, user is still banned, so unban them
            await guild.unban(user, reason="Temporary ban expired")
            
            # Try to DM the user about the unban (best effort)
            try:
                unban_embed = discord.Embed(
                    title=f"Your temporary ban from {guild.name} has expired",
                    description="You have been automatically unbanned and can now rejoin the server.",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                if guild.icon:
                    unban_embed.set_thumbnail(url=guild.icon.url)
                await user.send(embed=unban_embed)
                self.logger.info(f"Successfully sent auto-unban DM to {user} ({user.id})")
            except discord.Forbidden:
                self.logger.warning(f"Failed to send auto-unban DM to {user} ({user.id}) - user has DMs disabled or blocked the bot")
            except discord.HTTPException as e:
                self.logger.warning(f"Failed to send auto-unban DM to {user} ({user.id}) - HTTP error: {e}")
            except Exception as e:
                self.logger.warning(f"Failed to send auto-unban DM to {user} ({user.id}) - unexpected error: {e}")
            
            self.logger.info(f"Automatically unbanned {user} ({user.id}) from {guild.name} - tempban expired")
        except discord.NotFound:
            # User is not banned anymore
            pass
        except discord.Forbidden:
            self.logger.error(f"Failed to auto-unban {user} ({user.id}) from {guild.name} - missing permissions")
        except Exception as e:
            self.logger.error(f"Failed to auto-unban {user} ({user.id}) from {guild.name}: {e}")

    # Timeout
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="The member to timeout", duration="Duration (e.g., 30m, 1h, 2d)", reason="Reason for the timeout")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = "No reason provided"):
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
        if not has_moderation_permissions(interaction.user, member):
            return await interaction.response.send_message("❌ You don't have permission to timeout this member.", ephemeral=True)
        if not has_higher_role(interaction.guild.me, member):
            return await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)

        # Parse duration
        timeout_duration = self._parse_duration(duration)
        if not timeout_duration:
            return await interaction.response.send_message("❌ Invalid duration format. Use formats like: 30m, 1h, 2d", ephemeral=True)
        
        # Check if duration is within Discord's limits (max 28 days)
        max_duration = timedelta(days=28)
        if timeout_duration > max_duration:
            return await interaction.response.send_message("❌ Duration cannot exceed 28 days.", ephemeral=True)
            return await interaction.response.send_message("❌ I cannot timeout this member due to role hierarchy.", ephemeral=True)

        until = discord.utils.utcnow() + timeout_duration

        # DM best-effort
        try:
            dm = discord.Embed(
                title=f"You were timed out in {interaction.guild.name}",
                description=(
                    f"***Duration:*** {duration}\n"
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
            e.description += f"\n***Until:*** {discord.utils.format_dt(until, style='F')} • ***Duration:*** {duration}"
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
            e = self._dyno_style_embed("untimed out", member, reason)
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
            
            # Try to DM the user about the unban (best effort)
            try:
                unban_embed = discord.Embed(
                    title=f"You have been unbanned from {interaction.guild.name}",
                    description=f"You have been unbanned by a staff member and can now rejoin the server.\n\n**Reason:** {reason}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                if interaction.guild.icon:
                    unban_embed.set_thumbnail(url=interaction.guild.icon.url)
                await user.send(embed=unban_embed)
                self.logger.info(f"Successfully sent manual unban DM to {user} ({user.id})")
            except discord.Forbidden:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - user has DMs disabled or blocked the bot")
            except discord.HTTPException as e:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - HTTP error: {e}")
            except Exception as e:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - unexpected error: {e}")
            
            e = self._dyno_style_embed("unbanned", user, reason)
            e.set_footer(text=f"User ID: {user.id}")
            await interaction.response.send_message(embed=e)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID provided.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ User not found.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unban users.", ephemeral=True)

    # ------------------------------
    # Purge variants (slash)
    # ------------------------------
    @app_commands.command(name="purge", description="Delete recent messages (optionally from one user).")
    @app_commands.describe(amount="How many messages to scan (1–100)", user="Only delete messages from this user (optional)")
    async def purge(self, interaction: discord.Interaction, amount: int, user: Optional[discord.Member] = None):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        
        # Check if user has mod permissions (Discord perms OR mod whitelist)
        from utils.permissions import has_mod_permissions
        if not has_mod_permissions(interaction.user, self.bot, "manage_messages"):
            return await interaction.response.send_message("❌ You need **Manage Messages** permission or be on the mod whitelist.", ephemeral=True)
        
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            if user:
                def check(m: discord.Message):
                    return m.author == user
                deleted = await interaction.channel.purge(limit=amount * 2, check=check)
                await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages from {user.mention}.", ephemeral=True)
            else:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_attachments", description="Delete recent messages that contain attachments.")
    @app_commands.describe(amount="How many messages to scan (1–100)")
    async def purge_attachments(self, interaction: discord.Interaction, amount: int):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        
        # Check if user has mod permissions (Discord perms OR mod whitelist)
        from utils.permissions import has_mod_permissions
        if not has_mod_permissions(interaction.user, self.bot, "manage_messages"):
            return await interaction.response.send_message("❌ You need **Manage Messages** permission or be on the mod whitelist.", ephemeral=True)
        
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message):
                return bool(m.attachments)
            deleted = await interaction.channel.purge(limit=amount * 3, check=check)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages with attachments.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_invites", description="Delete recent messages that contain Discord invite links.")
    @app_commands.describe(amount="How many messages to scan (1–100)")
    async def purge_invites(self, interaction: discord.Interaction, amount: int):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        regex = self._invite_regex()
        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message):
                return bool(m.content and regex.search(m.content))
            deleted = await interaction.channel.purge(limit=amount * 3, check=check)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages containing invites.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_links", description="Delete recent messages that contain any URL.")
    @app_commands.describe(amount="How many messages to scan (1–100)")
    async def purge_links(self, interaction: discord.Interaction, amount: int):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        url_rx = self._url_regex()
        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message):
                return bool(m.content and url_rx.search(m.content))
            deleted = await interaction.channel.purge(limit=amount * 3, check=check)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages with links.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_bots", description="Delete recent messages sent by bots.")
    @app_commands.describe(amount="How many messages to scan (1–100)")
    async def purge_bots(self, interaction: discord.Interaction, amount: int):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message):
                return bool(m.author.bot)
            deleted = await interaction.channel.purge(limit=amount * 2, check=check)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** bot messages.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_text", description="Delete recent messages that contain a specific text (case-insensitive).")
    @app_commands.describe(amount="How many messages to scan (1–100)", query="Substring to match (case-insensitive)")
    async def purge_text(self, interaction: discord.Interaction, amount: int, query: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        if not query.strip():
            return await interaction.response.send_message("❌ Query cannot be empty.", ephemeral=True)

        needle = query.lower()
        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message):
                return bool(m.content and needle in m.content.lower())
            deleted = await interaction.channel.purge(limit=amount * 3, check=check)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages containing `{query}`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_before", description="Delete messages sent before a specific message.")
    @app_commands.describe(amount="How many messages to scan (1–100)", message_id="Message ID to use as the 'before' anchor")
    async def purge_before(self, interaction: discord.Interaction, amount: int, message_id: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id)
            anchor = await interaction.channel.fetch_message(mid)
        except Exception:
            return await interaction.followup.send("❌ Couldn't find that message ID in this channel.", ephemeral=True)

        try:
            deleted = await interaction.channel.purge(limit=amount, before=anchor)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages before [this message]({anchor.jump_url}).", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="purge_after", description="Delete messages sent after a specific message.")
    @app_commands.describe(amount="How many messages to scan (1–100)", message_id="Message ID to use as the 'after' anchor")
    async def purge_after(self, interaction: discord.Interaction, amount: int, message_id: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ You need **Manage Messages**.", ephemeral=True)
        if amount < 1 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id)
            anchor = await interaction.channel.fetch_message(mid)
        except Exception:
            return await interaction.followup.send("❌ Couldn't find that message ID in this channel.", ephemeral=True)

        try:
            deleted = await interaction.channel.purge(limit=amount, after=anchor)
            await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages after [this message]({anchor.jump_url}).", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

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
    async def prefix_ban(self, ctx, target, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        
        # Try to resolve the target (member, user ID, or fetch user)
        member = None
        user = None
        user_id = None
        
        # First, try to convert target to member if they're in the server
        try:
            # Try member converter first
            try:
                member_converter = commands.MemberConverter()
                member = await member_converter.convert(ctx, target)
                user = member
            except (commands.BadArgument, commands.MemberNotFound):
                # Member converter failed, try other methods
                # Try to parse as user ID
                if target.isdigit():
                    user_id = int(target)
                elif target.startswith('<@') and target.endswith('>'):
                    user_id = int(target.strip('<@!>'))
                else:
                    # Try to find member by username/display name
                    for m in ctx.guild.members:
                        if (m.name.lower() == target.lower() or 
                            m.display_name.lower() == target.lower()):
                            member = m
                            user = member
                            break
                    
                    if not member and not user_id:
                        return await ctx.send(
                            "❌ Could not find that user. Please provide a "
                            "valid user ID, mention, or username.", 
                            delete_after=5)
                
                # If we have a user ID but no member, try to fetch the user
                if user_id and not member:
                    member = ctx.guild.get_member(user_id)
                    if member:
                        user = member
                    else:
                        # User not in server, check permissions for hackban
                        if not ctx.author.guild_permissions.ban_members:
                            return await ctx.send(
                                "❌ You need ban permissions to ban users "
                                "not in the server.", delete_after=5)
                        
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except discord.NotFound:
                            return await ctx.send(
                                "❌ User not found.", delete_after=5)
                        except discord.HTTPException:
                            return await ctx.send(
                                "❌ Failed to fetch user information.", 
                                delete_after=5)
                            
        except ValueError:
            return await ctx.send("❌ Invalid user ID provided.", delete_after=5)
        
        # Ensure we have a user object at this point
        if not user:
            return await ctx.send(
                "❌ Could not resolve user. Please try again.", delete_after=5)
        
        # Permission checks for members in server
        if member:
            if not has_moderation_permissions(ctx.author, member):
                return await ctx.send(
                    "❌ You don't have permission to ban this member.",
                    delete_after=5)
            if not has_higher_role(ctx.guild.me, member):
                return await ctx.send(
                    "❌ I cannot ban this member due to role hierarchy.",
                    delete_after=5)

        # Check if user is already banned
        try:
            await ctx.guild.fetch_ban(user)
            return await ctx.send(
                f"❌ {user.mention} is already banned.", delete_after=5)
        except discord.NotFound:
            pass  # User is not banned, continue
        except discord.Forbidden:
            return await ctx.send(
                "❌ I don't have permission to check bans.", delete_after=5)

        # Try to DM the user (best effort, only if they're in server)
        if member:
            try:
                dm = discord.Embed(
                    title=f"You were banned from {ctx.guild.name}",
                    description=f"***Reason:*** {reason}",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                if ctx.guild.icon:
                    dm.set_thumbnail(url=ctx.guild.icon.url)
                await user.send(embed=dm)
            except Exception:
                pass

        try:
            await ctx.guild.ban(
                user, reason=f"Banned by {ctx.author}: {reason}")
            
            # Create success embed
            e = self._dyno_style_embed("banned", user, reason)
            e.set_footer(text=f"User ID: {user.id}")
            await ctx.send(embed=e)
            
        except discord.Forbidden:
            await ctx.send(
                "❌ I don't have permission to ban this user.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to ban user: {e}", delete_after=5)

    @commands.command(name="tempban")
    async def prefix_tempban(self, ctx, target: str, duration: str, *, reason="No reason provided"):
        """Temporarily ban a member or user from the server (prefix version)."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.", delete_after=5)
        if not isinstance(ctx.author, discord.Member):
            return await ctx.send("❌ You must be a member of this server to use this command.", delete_after=5)
        
        # Auto-delete command message
        await self.delete_command_message(ctx)
        
        # Parse duration
        ban_duration = self._parse_duration(duration)
        if not ban_duration:
            return await ctx.send("❌ Invalid duration format. Use formats like: 1h, 30m, 1d, 2w", delete_after=5)
        
        # Try to resolve the target (member, user ID, or fetch user)
        member = None
        user = None
        user_id = None
        
        # First, try to convert target to member if they're in the server
        try:
            # Try to get member by mention or ID
            if target.startswith('<@') and target.endswith('>'):
                user_id = int(target.strip('<@!>'))
            elif target.isdigit():
                user_id = int(target)
            else:
                # Try to find member by username/display name
                for m in ctx.guild.members:
                    if m.name.lower() == target.lower() or m.display_name.lower() == target.lower():
                        member = m
                        break
            
            if user_id and not member:
                member = ctx.guild.get_member(user_id)
            
        except ValueError:
            pass
        
        # If we found a member, do permission checks
        if member:
            if not has_moderation_permissions(ctx.author, member):
                return await ctx.send("❌ You don't have permission to ban this member.", delete_after=5)
            if not has_higher_role(ctx.guild.me, member):
                return await ctx.send("❌ I cannot ban this member due to role hierarchy.", delete_after=5)
            user = member
        else:
            # User not in server, try to fetch user object
            if not user_id:
                return await ctx.send("❌ Could not find that user. Please provide a valid user ID, mention, or username of someone in the server.", delete_after=5)
            
            # Check if user has ban permissions for hackbans
            if not ctx.author.guild_permissions.ban_members:
                return await ctx.send("❌ You need ban permissions to ban users not in the server.", delete_after=5)
            
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return await ctx.send("❌ User not found.", delete_after=5)
            except discord.HTTPException:
                return await ctx.send("❌ Failed to fetch user information.", delete_after=5)

        # Check if user is already banned
        try:
            ban_entry = await ctx.guild.fetch_ban(user)
            return await ctx.send(f"❌ {user.mention} is already banned.", delete_after=5)
        except discord.NotFound:
            pass  # User is not banned, continue
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to check bans.", delete_after=5)

        # Try to DM the user (best effort)
        if member:  # Only try to DM if they're in the server
            try:
                unban_time = discord.utils.utcnow() + ban_duration
                dm = discord.Embed(
                    title=f"You were temporarily banned from {ctx.guild.name}",
                    description=f"***Reason:*** {reason}\n***Duration:*** {duration}\n***Unban Time:*** <t:{int(unban_time.timestamp())}:F>",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                if ctx.guild.icon:
                    dm.set_thumbnail(url=ctx.guild.icon.url)
                await user.send(embed=dm)
            except Exception:
                pass

        try:
            await ctx.guild.ban(user, reason=f"Tempban by {ctx.author}: {reason} (Duration: {duration})", delete_message_days=0)
            
            # Schedule unban
            unban_time = discord.utils.utcnow() + ban_duration
            self.bot.loop.create_task(self._schedule_unban(ctx.guild, user, ban_duration))
            
            # Create success embed
            e = self._dyno_style_embed("temporarily banned", user, reason)
            e.description += f"\n***Duration:*** {duration}\n***Unban Time:*** <t:{int(unban_time.timestamp())}:R>"
            e.set_footer(text=f"User ID: {user.id}")
            await ctx.send(embed=e)
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban this user.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to ban user: {e}", delete_after=5)

    @commands.command(name="timeout")
    async def prefix_timeout(self, ctx, member: discord.Member, duration: str, *, reason="No reason provided"):
        await self.delete_command_message(ctx)
        
        # Parse duration
        timeout_duration = self._parse_duration(duration)
        if not timeout_duration:
            return await ctx.send("❌ Invalid duration format. Use formats like: 30m, 1h, 2d", delete_after=5)
        
        # Check if duration is within Discord's limits (max 28 days)
        max_duration = timedelta(days=28)
        if timeout_duration > max_duration:
            return await ctx.send("❌ Duration cannot exceed 28 days.", delete_after=5)
            
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return
        if not has_moderation_permissions(ctx.author, member):
            return await ctx.send("❌ You don't have permission to timeout this member.", delete_after=5)
        if not has_higher_role(ctx.guild.me, member):
            return await ctx.send("❌ I cannot timeout this member due to role hierarchy.", delete_after=5)

        until = discord.utils.utcnow() + timeout_duration

        try:
            dm = discord.Embed(
                title=f"You were timed out in {ctx.guild.name}",
                description=(
                    f"***Duration:*** {duration}\n"
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
            e.description += f"\n***Until:*** {discord.utils.format_dt(until, style='F')} • ***Duration:*** {duration}"
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
            e = self._dyno_style_embed("untimed out", member, reason)
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
            
            # Try to DM the user about the unban (best effort)
            try:
                unban_embed = discord.Embed(
                    title=f"You have been unbanned from {ctx.guild.name}",
                    description=f"You have been unbanned by a staff member and can now rejoin the server.\n\n**Reason:** {reason}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                if ctx.guild.icon:
                    unban_embed.set_thumbnail(url=ctx.guild.icon.url)
                await user.send(embed=unban_embed)
                self.logger.info(f"Successfully sent manual unban DM to {user} ({user.id})")
            except discord.Forbidden:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - user has DMs disabled or blocked the bot")
            except discord.HTTPException as e:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - HTTP error: {e}")
            except Exception as e:
                self.logger.warning(f"Failed to send manual unban DM to {user} ({user.id}) - unexpected error: {e}")
            
            e = self._dyno_style_embed("unbanned", user, reason)
            e.set_footer(text=f"User ID: {user.id}")
            await ctx.send(embed=e)
        except discord.NotFound:
            await ctx.send("❌ User not found.", delete_after=5)
        except discord.HTTPException as err:
            await ctx.send(f"❌ Failed to unban user: {err}", delete_after=5)

    # ------------------------------
    # Purge variants (prefix)
    # ------------------------------
    @commands.command(name="purge")
    @mod_check("manage_messages")
    async def p_purge(self, ctx, amount: int, member: Optional[discord.Member] = None):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        try:
            if member:
                def check(m: discord.Message):
                    return m.author == member
                deleted = await ctx.channel.purge(limit=amount * 2, check=check)
                await ctx.send(f"🧹 Deleted **{len(deleted)}** messages from {member.mention}", delete_after=5)
            else:
                deleted = await ctx.channel.purge(limit=amount)
                await ctx.send(f"🧹 Deleted **{len(deleted)}** messages", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgeattachments")
    @mod_check("manage_messages")
    async def p_purge_attachments(self, ctx, amount: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        try:
            def check(m: discord.Message):
                return bool(m.attachments)
            deleted = await ctx.channel.purge(limit=amount * 3, check=check)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages with attachments", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgeinvites")
    @mod_check("manage_messages")
    async def p_purge_invites(self, ctx, amount: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        regex = self._invite_regex()
        try:
            def check(m: discord.Message):
                return bool(m.content and regex.search(m.content))
            deleted = await ctx.channel.purge(limit=amount * 3, check=check)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages containing invites", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgelinks")
    @mod_check("manage_messages")
    async def p_purge_links(self, ctx, amount: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        url_rx = self._url_regex()
        try:
            def check(m: discord.Message):
                return bool(m.content and url_rx.search(m.content))
            deleted = await ctx.channel.purge(limit=amount * 3, check=check)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages with links", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgebots")
    @mod_check("manage_messages")
    async def p_purge_bots(self, ctx, amount: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        try:
            def check(m: discord.Message):
                return bool(m.author.bot)
            deleted = await ctx.channel.purge(limit=amount * 2, check=check)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** bot messages", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgetext")
    @mod_check("manage_messages")
    async def p_purge_text(self, ctx, amount: int, *, query: str):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        if not query.strip():
            return await ctx.send("❌ Query cannot be empty.", delete_after=5)
        needle = query.lower()
        try:
            def check(m: discord.Message):
                return bool(m.content and needle in m.content.lower())
            deleted = await ctx.channel.purge(limit=amount * 3, check=check)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages containing `{query}`", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgebefore")
    @mod_check("manage_messages")
    async def p_purge_before(self, ctx, amount: int, message_id: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        try:
            anchor = await ctx.channel.fetch_message(int(message_id))
        except Exception:
            return await ctx.send("❌ Couldn't find that message ID in this channel.", delete_after=5)
        try:
            deleted = await ctx.channel.purge(limit=amount, before=anchor)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages before that message", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)

    @commands.command(name="purgeafter")
    @mod_check("manage_messages")
    async def p_purge_after(self, ctx, amount: int, message_id: int):
        await self.delete_command_message(ctx)
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Amount must be between 1 and 100.", delete_after=5)
        try:
            anchor = await ctx.channel.fetch_message(int(message_id))
        except Exception:
            return await ctx.send("❌ Couldn't find that message ID in this channel.", delete_after=5)
        try:
            deleted = await ctx.channel.purge(limit=amount, after=anchor)
            await ctx.send(f"🧹 Deleted **{len(deleted)}** messages after that message", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=5)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(ModerationCog(bot))