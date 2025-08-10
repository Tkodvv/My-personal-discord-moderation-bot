"""
Moderation Cog
Contains all moderation-related slash commands like kick, ban, timeout, etc.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
from typing import Optional, Dict, Any


from utils.permissions import has_moderation_permissions, has_higher_role


class ModerationCog(commands.Cog):
    """Moderation commands cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

        # In-memory case store: { guild_id: { case_id: {...} } }
        self._cases: Dict[int, Dict[int, Dict[str, Any]]] = {}
        # Per-guild counters: { guild_id: next_case_number_int }
        self._case_counter: Dict[int, int] = {}

    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # ---- Case helpers ----
    def _next_case_id(self, guild_id: int) -> int:
        n = self._case_counter.get(guild_id, 1)
        self._case_counter[guild_id] = n + 1
        return n

    def _store_case(
        self,
        guild_id: int,
        case_id: int,
        *,
        action: str,
        target_id: int,
        target_tag: str,
        moderator_id: int,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        self._cases.setdefault(guild_id, {})
        self._cases[guild_id][case_id] = {
            "action": action,
            "target_id": target_id,
            "target_tag": target_tag,
            "moderator_id": moderator_id,
            "reason": reason,
            "extra": extra or {},
        }

    def _get_case(self, guild_id: int, case_id: int) -> Optional[Dict[str, Any]]:
        return self._cases.get(guild_id, {}).get(case_id)

    def _update_case_reason(self, guild_id: int, case_id: int, new_reason: str) -> Optional[str]:
        c = self._get_case(guild_id, case_id)
        if not c:
            return None
        old = c.get("reason") or "No reason provided"
        c["reason"] = new_reason
        return old

    # ---- Brand helpers (Dyno-style card) ----
    def _brand_color(self) -> discord.Color:
        # Your brand: green everywhere on public mod cards
        return discord.Color.green()

    def _action_embed(self, guild: Optional[discord.Guild], title: str, case_id: Optional[int] = None, footer_user_id: Optional[int] = None) -> discord.Embed:
        e = discord.Embed(
            title=title,
            color=self._brand_color(),
            timestamp=discord.utils.utcnow()
        )
        # Dyno-like header
        if guild and guild.icon:
            e.set_author(name=f"{guild.name} • Moderation", icon_url=guild.icon.url)
        else:
            e.set_author(name="Moderation")

        # Footer shows Case ID and User ID (Dyno vibe)
        footer_bits = []
        if case_id is not None:
            footer_bits.append(f"Case #{case_id}")
        if footer_user_id is not None:
            footer_bits.append(f"User ID: {footer_user_id}")
        if footer_bits:
            e.set_footer(text=" • ".join(footer_bits))
        return e

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

        # Case id
        case_id = self._next_case_id(interaction.guild.id)

        # Try to DM first (best-effort)
        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were kicked from {interaction.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False
        
        try:
            # Log the action
            self.logger.info(f"[Case #{case_id}] Kick: {interaction.user} -> {member} in {interaction.guild.name} (dm_sent={dm_sent})")
            
            # Perform the kick
            await member.kick(reason=f"Kicked by staff: {reason}")
            
            # Store case
            self._store_case(
                interaction.guild.id,
                case_id,
                action="Kick",
                target_id=member.id,
                target_tag=f"{member} ",
                moderator_id=interaction.user.id,
                reason=reason,
                extra={"dm_sent": dm_sent},
            )

            # Public confirmation (Dyno-style card)
            embed = self._action_embed(interaction.guild, "Kick", case_id, member.id)
            embed.description = f"**{member.display_name}** has been kicked from the server."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)

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
        
        # Case id
        case_id = self._next_case_id(interaction.guild.id)

        # Try to DM first (best-effort)
        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were banned from {interaction.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False
        
        try:
            # Log the action
            self.logger.info(f"[Case #{case_id}] Ban: {interaction.user} -> {member} in {interaction.guild.name} | delete_days={delete_messages} | reason={reason} (dm_sent={dm_sent})")
            
            # Perform the ban
            await member.ban(
                reason=f"Banned by staff: {reason}",
                delete_message_days=delete_messages or 0
            )
            
            # Store case
            self._store_case(
                interaction.guild.id,
                case_id,
                action="Ban",
                target_id=member.id,
                target_tag=f"{member} ",
                moderator_id=interaction.user.id,
                reason=reason,
                extra={"dm_sent": dm_sent, "delete_days": delete_messages or 0},
            )

            # Public confirmation (Dyno-style card)
            embed = self._action_embed(interaction.guild, "Ban", case_id, member.id)
            embed.description = f"**{member.display_name}** has been banned from the server."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            if delete_messages and delete_messages > 0:
                embed.add_field(name="Messages Deleted", value=f"{delete_messages} days", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
            
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
        case_id = self._next_case_id(interaction.guild.id)

        # Try to DM first (best-effort)
        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were timed out in {interaction.guild.name}",
                description=f"**Duration:** {duration} minutes\n**Until:** <t:{int(timeout_until.timestamp())}:F>\n**Reason:** {reason}",
                color=discord.Color.yellow(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False
        
        try:
            self.logger.info(f"[Case #{case_id}] Timeout: {interaction.user} -> {member} for {duration} minutes in {interaction.guild.name} (dm_sent={dm_sent})")
            
            # Perform the timeout
            await member.timeout(timeout_until, reason=f"Timed out by staff: {reason}")

            # Store case
            self._store_case(
                interaction.guild.id,
                case_id,
                action="Timeout",
                target_id=member.id,
                target_tag=f"{member} ",
                moderator_id=interaction.user.id,
                reason=reason,
                extra={"dm_sent": dm_sent, "minutes": duration, "until": int(timeout_until.timestamp())},
            )
            
            # Public confirmation (Dyno-style card)
            embed = self._action_embed(interaction.guild, "Timeout", case_id, member.id)
            embed.description = f"**{member.display_name}** has been timed out."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
            embed.add_field(name="Until", value=f"<t:{int(timeout_until.timestamp())}:f>", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
            
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
        
        # Case id
        case_id = self._next_case_id(interaction.guild.id)

        # Try to DM (best-effort)
        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"Your timeout was removed in {interaction.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if interaction.guild.icon:
                dm_embed.set_thumbnail(url=interaction.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        try:
            self.logger.info(f"[Case #{case_id}] Untimeout: {interaction.user} -> {member} in {interaction.guild.name} (dm_sent={dm_sent})")
            
            # Remove the timeout
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")

            # Store case
            self._store_case(
                interaction.guild.id,
                case_id,
                action="Untimeout",
                target_id=member.id,
                target_tag=f"{member} ",
                moderator_id=interaction.user.id,
                reason=reason,
                extra={"dm_sent": dm_sent},
            )

            # Public confirmation (Dyno-style card)
            embed = self._action_embed(interaction.guild, "Timeout Removed", case_id, member.id)
            embed.description = f"**{member.display_name}**'s timeout has been removed."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
            
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
            
            # Case id
            case_id = self._next_case_id(interaction.guild.id)

            self.logger.info(f"[Case #{case_id}] Unban: {interaction.user} -> {user_id} in {interaction.guild.name}")
            
            # Unban first to avoid failures after the response
            await interaction.guild.unban(user, reason=f"Unbanned by staff: {reason}")

            # Store case
            self._store_case(
                interaction.guild.id,
                case_id,
                action="Unban",
                target_id=user.id,
                target_tag=f"{user} ",
                moderator_id=interaction.user.id,
                reason=reason,
                extra={},
            )

            embed = self._action_embed(interaction.guild, "Unban", case_id, user.id)
            embed.description = f"**{user.display_name}** has been unbanned from the server."
            embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            
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
    # /reason — edit a case reason
    # --------------------
    @app_commands.command(name="reason", description="Update the reason for a moderation case (Case ID).")
    @app_commands.describe(
        case_id="The Case # to edit",
        reason="The new reason text"
    )
    async def reason_cmd(self, interaction: discord.Interaction, case_id: int, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Basic permission gate similar to Dyno (any mod perms is fine)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ You must be a member of this server to use this command.", ephemeral=True)
            return

        if not (
            member.guild_permissions.kick_members
            or member.guild_permissions.ban_members
            or member.guild_permissions.moderate_members
            or member.guild_permissions.manage_messages
        ):
            await interaction.response.send_message("❌ You don't have permission to edit case reasons.", ephemeral=True)
            return

        old = self._update_case_reason(interaction.guild.id, case_id, reason)
        if old is None:
            await interaction.response.send_message("❌ Case not found.", ephemeral=True)
            return

        # Build a tidy confirmation card
        c = self._get_case(interaction.guild.id, case_id)
        target_id = c.get("target_id")
        action = c.get("action", "Case")
        embed = self._action_embed(interaction.guild, "Reason Updated", case_id, target_id)
        embed.add_field(name="Action", value=action, inline=True)
        embed.add_field(name="Old Reason", value=old[:1024] if old else "No reason provided", inline=False)
        embed.add_field(name="New Reason", value=reason[:1024], inline=False)

        await interaction.response.send_message(embed=embed)

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
        
        case_id = self._next_case_id(ctx.guild.id)

        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were kicked from {ctx.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        try:
            await member.kick(reason=f"Kicked by staff: {reason}")

            self._store_case(
                ctx.guild.id, case_id, action="Kick",
                target_id=member.id, target_tag=f"{member} ",
                moderator_id=ctx.author.id, reason=reason, extra={"dm_sent": dm_sent}
            )

            embed = self._action_embed(ctx.guild, "Kick", case_id, member.id)
            embed.description = f"**{member.display_name}** has been kicked."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
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

        case_id = self._next_case_id(ctx.guild.id)

        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were banned from {ctx.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        try:
            await member.ban(reason=f"Banned by staff: {reason}")

            self._store_case(
                ctx.guild.id, case_id, action="Ban",
                target_id=member.id, target_tag=f"{member} ",
                moderator_id=ctx.author.id, reason=reason, extra={"dm_sent": dm_sent}
            )

            embed = self._action_embed(ctx.guild, "Ban", case_id, member.id)
            embed.description = f"**{member.display_name}** has been banned."
            embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
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
        case_id = self._next_case_id(ctx.guild.id)

        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"You were timed out in {ctx.guild.name}",
                description=f"**Duration:** {minutes} minutes\n**Until:** <t:{int(until.timestamp())}:F>\n**Reason:** {reason}",
                color=discord.Color.yellow(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        try:
            await member.timeout(until, reason=f"Timed out by staff: {reason}")

            self._store_case(
                ctx.guild.id, case_id, action="Timeout",
                target_id=member.id, target_tag=f"{member} ",
                moderator_id=ctx.author.id, reason=reason,
                extra={"dm_sent": dm_sent, "minutes": minutes, "until": int(until.timestamp())}
            )

            e = self._action_embed(ctx.guild, "Timeout", case_id, member.id)
            e.description = f"**{member.display_name}** has been timed out."
            e.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            e.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
            e.add_field(name="Until", value=f"<t:{int(until.timestamp())}:f>", inline=True)
            e.add_field(name="Reason", value=reason, inline=False)
            e.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
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

        case_id = self._next_case_id(ctx.guild.id)

        dm_sent = False
        try:
            dm_embed = discord.Embed(
                title=f"Your timeout was removed in {ctx.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
            dm_sent = True
        except Exception:
            dm_sent = False

        try:
            await member.timeout(None, reason=f"Timeout removed by staff: {reason}")

            self._store_case(
                ctx.guild.id, case_id, action="Untimeout",
                target_id=member.id, target_tag=f"{member} ",
                moderator_id=ctx.author.id, reason=reason, extra={"dm_sent": dm_sent}
            )

            e = self._action_embed(ctx.guild, "Timeout Removed", case_id, member.id)
            e.description = f"**{member.display_name}**'s timeout has been removed."
            e.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
            e.add_field(name="Reason", value=reason, inline=False)
            e.add_field(name="DM Sent", value="Yes ✅" if dm_sent else "No ❌", inline=True)
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

            # Case id
            case_id = self._next_case_id(ctx.guild.id)

            # Unban
            await ctx.guild.unban(user, reason=f"Unbanned by staff: {reason}")

            self._store_case(
                ctx.guild.id, case_id, action="Unban",
                target_id=user.id, target_tag=f"{user} ",
                moderator_id=ctx.author.id, reason=reason, extra={}
            )

            # Public confirmation (Dyno-style card)
            embed = self._action_embed(ctx.guild, "Unban", case_id, user.id)
            embed.description = f"**{user.display_name}** has been unbanned from the server."
            embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)

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