""" 
Admin Cog
Contains administrative commands like say, announce, clear, prefix management,
and per-guild bot-mod role management (persistent).
"""

import logging
import io
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
from discord.utils import utcnow, format_dt

class AdminCog(commands.Cog):
    """Administrative commands cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        # Store deleted messages for snipe command
        self.deleted_messages = {}

        # Allowed roles for /say (you can remove this if you want to fully rely on modlist)
        self.allowed_say_roles = {
            1383421890403762286,
            1349191381310111824,
            1379755293797384202,
        }
    
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

    # =========================================================
    # Bot modlist management (per-guild, persistent) – SLASH
    # =========================================================

    @app_commands.command(name="addmod", description="Add a role to this guild's bot-mod list (members with it can use the bot).")
    @app_commands.describe(role="Role to add")
    async def addmod(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need **Administrator** to use this.", ephemeral=True)
            return

        self.bot.add_guild_mod_role(interaction.guild.id, role.id)
        current_ids = self.bot.get_guild_mod_role_ids(interaction.guild.id)

        mentions = []
        for rid in current_ids:
            r = interaction.guild.get_role(rid)
            if r:
                mentions.append(r.mention)
        text = ", ".join(mentions) if mentions else "_(none)_"

        await interaction.response.send_message(
            f"✅ Added {role.mention}.\n**Current mod roles:** {text}",
            ephemeral=True
        )

    @app_commands.command(name="removemod", description="Remove a role from this guild's bot-mod list.")
    @app_commands.describe(role="Role to remove")
    async def removemod(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need **Administrator** to use this.", ephemeral=True)
            return

        removed = self.bot.remove_guild_mod_role(interaction.guild.id, role.id)
        if not removed:
            await interaction.response.send_message("ℹ️ That role wasn’t on the mod list.", ephemeral=True)
            return

        current_ids = self.bot.get_guild_mod_role_ids(interaction.guild.id)
        mentions = []
        for rid in current_ids:
            r = interaction.guild.get_role(rid)
            if r:
                mentions.append(r.mention)
        text = ", ".join(mentions) if mentions else "_(none)_"

        await interaction.response.send_message(
            f"✅ Removed {role.mention}.\n**Current mod roles:** {text}",
            ephemeral=True
        )

    @app_commands.command(name="listmods", description="Show this guild's bot-mod roles.")
    async def listmods(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return

        ids = self.bot.get_guild_mod_role_ids(interaction.guild.id)

        mentions = []
        missing = []
        for rid in ids:
            r = interaction.guild.get_role(rid)
            if r:
                mentions.append(r.mention)
            else:
                missing.append(rid)

        lines = []
        lines.append("**Mod roles:** " + (", ".join(mentions) if mentions else "_(none)_"))
        if missing:
            lines.append("**Dangling IDs (role deleted?):** " + ", ".join(str(x) for x in missing))

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # =========================================================
    # Bot modlist management – PREFIX
    # =========================================================

    @commands.command(name="addmod")
    @commands.has_permissions(administrator=True)
    async def p_addmod(self, ctx, role: discord.Role):
        self.bot.add_guild_mod_role(ctx.guild.id, role.id)
        await self.delete_command_message(ctx)
        await ctx.send(f"✅ Added {role.mention} to the bot-mod list.", delete_after=5)

    @commands.command(name="removemod")
    @commands.has_permissions(administrator=True)
    async def p_removemod(self, ctx, role: discord.Role):
        removed = self.bot.remove_guild_mod_role(ctx.guild.id, role.id)
        await self.delete_command_message(ctx)
        msg = "✅ Removed." if removed else "ℹ️ That role wasn’t on the list."
        await ctx.send(msg, delete_after=5)

    @commands.command(name="modlist")
    @commands.has_permissions(manage_guild=True)
    async def p_modlist(self, ctx):
        await self.delete_command_message(ctx)
        ids = self.bot.get_guild_mod_role_ids(ctx.guild.id)
        mentions = [r.mention for r in (ctx.guild.get_role(i) for i in ids) if r]
        text = ", ".join(mentions) if mentions else "_(none)_"
        await ctx.send("**Mod roles:** " + text, delete_after=10)

    # =========================
    # /say (text + attachments)
    # =========================
    @app_commands.command(name="say", description="Make the bot say something (and send attached images/files).")
    @app_commands.describe(
        message="What should I say? (can be empty if only sending files)",
        channel="Channel to send to (default: here)",
        file1="Attach image/file (optional)",
        file2="Attach image/file (optional)",
        file3="Attach image/file (optional)",
        file4="Attach image/file (optional)",
        file5="Attach image/file (optional)",
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str = "",
        channel: Optional[discord.TextChannel] = None,
        file1: Optional[discord.Attachment] = None,
        file2: Optional[discord.Attachment] = None,
        file3: Optional[discord.Attachment] = None,
        file4: Optional[discord.Attachment] = None,
        file5: Optional[discord.Attachment] = None,
    ):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        has_role = any((role.id in self.allowed_say_roles) for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message("❌ You don't have access to `/say`.", ephemeral=True)
            return

        target = channel or interaction.channel

        atts = [a for a in (file1, file2, file3, file4, file5) if a is not None]
        files: list[discord.File] = []
        for a in atts:
            try:
                data = await a.read()
                files.append(discord.File(io.BytesIO(data), filename=a.filename))
            except Exception:
                pass

        content = message.strip() or None
        if not content and not files:
            await interaction.response.send_message("❌ Nothing to send. Add text or attach at least one file.", ephemeral=True)
            return

        self.logger.info(f"Say command used by {interaction.user} in {interaction.guild.name}")

        try:
            await target.send(content=content, files=files or None)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send: {e}", ephemeral=True)
            return

        if not interaction.response.is_done():
            if target != interaction.channel:
                await interaction.response.send_message(f"✅ Sent to {target.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Sent.", ephemeral=True)
    
    # =========================
    # /announce (title optional, message required, optional role ping)
    # =========================
    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(
        message="The announcement message (required)",
        title="Title of the announcement (optional)",
        channel="Channel to send the announcement to (optional)",
        ping_role="Role to ping above the embed (optional)"
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        title: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        ping_role: Optional[discord.Role] = None,
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        target_channel = channel or interaction.channel

        embed = discord.Embed(
            title=title or None,  # ✅ fixed to avoid Embed.Empty
            description=message,
            color=discord.Color.green()
        )

        self.logger.info(
            f"Announce command used by {interaction.user} in {interaction.guild.name} "
            f"(title={'yes' if title else 'no'}, ping_role={getattr(ping_role, 'id', None)})"
        )
        
        try:
            content = ping_role.mention if ping_role else None
            allowed = discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=[ping_role] if ping_role else True
            )

            await target_channel.send(content=content, embed=embed, allowed_mentions=allowed)

            note = f" (pinged {ping_role.mention})" if ping_role else ""
            if target_channel != interaction.channel:
                await interaction.response.send_message(f"✅ Announcement sent to {target_channel.mention}{note}", ephemeral=True)
            else:
                await interaction.response.send_message(f"✅ Announcement sent!{note}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send announcement: {e}", ephemeral=True)