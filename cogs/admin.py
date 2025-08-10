"""
Admin Cog
Contains administrative commands like say, announce, clear, prefix management,
and per‑guild bot-mod role management (persistent).
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
    # Bot modlist management (per‑guild, persistent) – SLASH
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
        """Say text + any attached images/files, restricted to specific roles."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # If you want /say to respect the persistent mod list instead, replace this block
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
    
    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(
        title="Title of the announcement",
        message="The announcement message",
        channel="Channel to send the announcement to (optional)"
    )
    async def announce(self, interaction: discord.Interaction, title: str, message: str, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        embed = discord.Embed(title=title, description=message, color=discord.Color.green())

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
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used by server members.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if user:
                def check(message):
                    return message.author == user
                deleted = await interaction.channel.purge(limit=amount * 2, check=check)
                deleted_count = len(deleted)
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages from {user.mention}", ephemeral=True)
            else:
                deleted = await interaction.channel.purge(limit=amount)
                deleted_count = len(deleted)
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages", ephemeral=True)
            
            self.logger.info(f"Clear command used by {interaction.user} - deleted {deleted_count} messages in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to delete messages: {e}", ephemeral=True)
    
    @app_commands.command(name="snipe", description="Show the last deleted message in this channel")
    async def snipe(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        
        if channel_id not in self.deleted_messages:
            await interaction.response.send_message("❌ No recently deleted messages found in this channel.", ephemeral=True)
            return
        
        deleted_msg = self.deleted_messages[channel_id]
        
        embed = discord.Embed(
            title="🎯 Sniped Message",
            description=deleted_msg['content'] or "*No content*",
            color=discord.Color.orange()
        )
        embed.set_author(
            name=deleted_msg['author'].display_name,
            icon_url=deleted_msg['author'].display_avatar.url
        )
        embed.add_field(name="Sent", value=format_dt(deleted_msg['created_at'], style="F"), inline=False)
        embed.set_footer(text="Message deleted")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="setprefix", description="Change the bot's command prefix")
    @app_commands.describe(prefix="New prefix for the bot (max 5 characters)")
    async def setprefix(self, interaction: discord.Interaction, prefix: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to change the prefix.", ephemeral=True)
            return
        
        if len(prefix) > 5:
            await interaction.response.send_message("❌ Prefix must be 5 characters or less.", ephemeral=True)
            return
        
        self.bot.command_prefix = prefix
        
        embed = discord.Embed(
            title="✅ Prefix Changed",
            description=f"Bot prefix has been changed to `{prefix}`",
            color=discord.Color.green()
        )
        embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
        embed.set_footer(text=f"Changed by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        self.logger.info(f"Prefix changed to '{prefix}' by {interaction.user} in {interaction.guild.name}")
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="dm", description="Send a direct message to a user")
    @app_commands.describe(user="The user to send a DM to", message="The message to send")
    async def dm_user(self, interaction: discord.Interaction, user: discord.User, *, message: str):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            await user.send(message)
            await interaction.response.send_message(f"✅ Direct message sent to {user.display_name}!", ephemeral=True)
            self.logger.info(f"DM sent to {user} by {interaction.user} in {interaction.guild.name}: {message}")
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ Could not send DM to {user.display_name}. They may have DMs disabled or blocked the bot.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to send DM: {e}", ephemeral=True)
            self.logger.error(f"Failed to send DM to {user}: {e}")
    
    @app_commands.command(name="setnick", description="Change a member's nickname")
    @app_commands.describe(member="The member to change nickname for", nickname="The new nickname (leave empty to remove nickname)")
    async def setnick(self, interaction: discord.Interaction, member: discord.Member, nickname: Optional[str] = None):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_nicknames:
            await interaction.response.send_message("❌ You don't have permission to manage nicknames.", ephemeral=True)
            return
        
        if member.top_role >= interaction.guild.me.top_role and member != interaction.guild.me:
            await interaction.response.send_message("❌ I cannot change this member's nickname due to role hierarchy.", ephemeral=True)
            return
        
        try:
            old_nick = member.display_name
            await member.edit(nick=nickname)
            
            embed = discord.Embed(title="✅ Nickname Changed", color=discord.Color.green())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Old Nickname", value=old_nick, inline=True)
            embed.add_field(name="New Nickname", value=nickname or member.name, inline=True)
            embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
            embed.set_footer(text=f"Changed by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed)
            self.logger.info(f"Nickname changed for {member} by {interaction.user}: {old_nick} -> {nickname or member.name}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to change this member's nickname.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to change nickname: {e}", ephemeral=True)
    
    @app_commands.command(name="addrole", description="Add a role to a member")
    @app_commands.describe(member="The member to add the role to", role="The role to add")
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return
        
        if role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("❌ You cannot assign a role that is higher than or equal to your highest role.", ephemeral=True)
            return
        
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I cannot assign this role due to role hierarchy.", ephemeral=True)
            return
        
        if role in member.roles:
            await interaction.response.send_message(f"ℹ️ {member.display_name} already has the {role.name} role.", ephemeral=True)
            return
        
        try:
            await member.add_roles(role)
            embed = discord.Embed(title="✅ Role Added", color=discord.Color.green())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Role Added", value=role.mention, inline=True)
            embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
            embed.set_footer(text=f"Added by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
            self.logger.info(f"Role {role.name} added to {member} by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to add this role.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to add role: {e}", ephemeral=True)
    
    @app_commands.command(name="watchuser", description="Add a user to the watch list for monitoring")
    @app_commands.describe(user="The user to add to watch list", reason="Reason for watching this user")
    async def watchuser(self, interaction: discord.Interaction, user: discord.User, *, reason: str = "No reason provided"):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not hasattr(self, 'watch_list'):
            self.watch_list = {}
        
        guild_id = interaction.guild.id
        if guild_id not in self.watch_list:
            self.watch_list[guild_id] = {}
        
        self.watch_list[guild_id][user.id] = {
            'user': user,
            'reason': reason,
            'added_by': interaction.user,
            'added_at': utcnow()
        }
        
        embed = discord.Embed(title="🕵️‍♂️ User Added to Watch List", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{user.mention} ({user.name}#{user.discriminator})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
        embed.set_footer(text=f"Added by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
        self.logger.info(f"User {user} added to watch list by {interaction.user} - Reason: {reason}")

    # =========================
    # Prefix command versions already present
    # =========================
    @commands.command(name="say")
    async def prefix_say(self, ctx, *, message):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member):
            return
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=5)
            return
        await ctx.send(message)
    
    @commands.command(name="clear")
    async def prefix_clear(self, ctx, amount: int, member: Optional[discord.Member] = None):
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
        await self.delete_command_message(ctx)
        channel_id = ctx.channel.id
        if channel_id not in self.deleted_messages:
            await ctx.send("❌ No recently deleted messages found.", delete_after=5)
            return
        deleted_msg = self.deleted_messages[channel_id]
        embed = discord.Embed(
            title="🎯 Sniped Message",
            description=deleted_msg['content'] or "*No content*",
            color=discord.Color.orange()
        )
        embed.set_author(
            name=deleted_msg['author'].display_name,
            icon_url=deleted_msg['author'].display_avatar.url
        )
        embed.add_field(name="Sent", value=format_dt(deleted_msg['created_at'], style="F"), inline=False)
        await ctx.send(embed=embed)
    
    @commands.command(name="dm")
    async def prefix_dm(self, ctx, user: discord.User, *, message):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member):
            return
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=5)
            return
        try:
            await user.send(message)
            confirmation = await ctx.send(f"✅ Direct message sent to {user.display_name}!")
            await confirmation.delete(delay=3)
            self.logger.info(f"DM sent to {user} by {ctx.author} in {ctx.guild.name}: {message}")
        except discord.Forbidden:
            await ctx.send(f"❌ Could not send DM to {user.display_name}. They may have DMs disabled or blocked the bot.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to send DM: {e}", delete_after=5)
            self.logger.error(f"Failed to send DM to {user}: {e}")

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(AdminCog(bot))
