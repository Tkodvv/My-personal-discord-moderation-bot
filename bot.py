"""
Discord Bot Main Class
Contains the main bot class with event handlers and cog loading.
"""

import logging
import json
import os
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Dict, List, Set
from discord.utils import utcnow, format_dt

# === OPTIONAL: Legacy global role IDs fallback ===
ALLOWED_ROLE_IDS = {
    1383421890403762286,
    1349191381310111824,
    1379755293797384202,
}

class DiscordBot(commands.Bot):
    """Main Discord bot class with slash command support and per-guild mod/alt whitelists."""

    # ---------- persistence paths ----------
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    MOD_FILE = os.path.join(DATA_DIR, "mod_whitelist.json")
    ALT_FILE = os.path.join(DATA_DIR, "alt_whitelist.json")

    def __init__(self):
        # Setup required intents
        intents = discord.Intents.default()
        intents.message_content = True  # Needed for prefix commands
        intents.members = True  # Needed for member cache
        intents.guilds = True   # Needed for guild operations
        intents.presences = True  # Needed for status commands

        # Initialize with fixed "!" prefix
        self._text_prefix = "!"
        
        def get_prefix(bot, message):
            # Always allow mention and "!" prefix
            return commands.when_mentioned_or("!")(bot, message)
        
        super().__init__(
            command_prefix=get_prefix,  # Use the prefix getter function
            intents=intents,
            help_command=None,
            case_insensitive=True,
            chunk_guilds_at_startup=True,  # Enable chunking for member caching
            member_cache_flags=discord.MemberCacheFlags.all(),  # Cache all member data
            max_messages=1000
        )
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)

        # ---- runtime state / persistence containers (MOVED OUT OF on_message) ----
        self.mod_whitelist: Dict[str, List[int]] = {}
        self.alt_whitelist_users: Dict[int, Set[int]] = {}
        self.alt_whitelist_roles: Dict[int, Set[int]] = {}   # <-- was 'bot.alt_whitelist_roles' (fixed)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.load_mod_whitelist()
        self.load_alt_whitelist()

        # health/uptime tracking
        self.boot_time = utcnow()
        self.last_sync_time = None

        # optional flag some cogs check
        self._did_tree_sync = False

    @tasks.loop(minutes=5)  # Ping every 5 minutes to keep alive
    async def keep_alive_task(self):
        """Keep-alive task to prevent VS Code from timing out the bot."""
        try:
            # Simple ping to Discord API to maintain connection
            latency = round(self.latency * 1000, 2)
            self.logger.debug(f"Keep-alive ping - Latency: {latency}ms")
            
            # Optional: Send a heartbeat message to console every hour
            if hasattr(self, '_keep_alive_counter'):
                self._keep_alive_counter += 1
                if self._keep_alive_counter >= 12:  # 12 * 5 minutes = 1 hour
                    self.logger.info(f"Bot keep-alive heartbeat - Uptime: {self._get_uptime_string()}")
                    self._keep_alive_counter = 0
            else:
                self._keep_alive_counter = 0
                
        except Exception as e:
            self.logger.warning(f"Keep-alive task error: {e}")

    @keep_alive_task.before_loop
    async def before_keep_alive_task(self):
        """Wait until the bot is ready before starting the keep-alive task."""
        await self.wait_until_ready()
        self.logger.info("Keep-alive task started")

    def _get_uptime_string(self) -> str:
        """Get a formatted uptime string."""
        delta = utcnow() - self.boot_time
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    async def setup_hook(self):
        """Load extensions and sync commands when the bot starts."""
        # Load all cogs
        for filename in os.listdir("cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    self.logger.info(f"Loaded extension: {filename[:-3]}")
                except Exception as e:
                    self.logger.error(f"Failed to load extension {filename}: {e}")
                    
        # Sync all commands
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} slash commands")
            self._did_tree_sync = True
            self.last_sync_time = utcnow()
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")
            
        # Start the keep-alive task
        if not self.keep_alive_task.is_running():
            self.keep_alive_task.start()
            self.logger.info("Keep-alive task initialized")

    # ---------- message handling ----------
    async def on_message(self, message: discord.Message):
        """Process commands and handle prefix command deletion."""
        # Always ignore bot messages first
        if message.author.bot:
            return

        # Log DM replies to bot (only from non-bot users)
        if isinstance(message.channel, discord.DMChannel):
            await self._log_dm_reply(message)

        # Process all commands normally
        await self.process_commands(message)

    async def _log_dm_reply(self, message: discord.Message):
        """Log when users reply to the bot in DMs."""
        try:
            # Log to console/file
            content_preview = message.content[:100]
            if len(message.content) > 100:
                content_preview += "..."
            
            self.logger.info(
                "DM Reply from %s (%s): %s",
                message.author.display_name,
                message.author.id,
                content_preview
            )
            
            # Try to find a logging channel in any guild the bot is in
            for guild in self.guilds:
                # Look for common logging channel names
                log_channel = None
                channel_names = [
                    'mod-logs', 'bot-logs', 'logs', 'moderation-logs'
                ]
                for channel_name in channel_names:
                    log_channel = discord.utils.get(
                        guild.channels, name=channel_name
                    )
                    if (log_channel and
                            isinstance(log_channel, discord.TextChannel)):
                        break
                
                if log_channel:
                    # Create embed for DM reply
                    embed = discord.Embed(
                        title="📩 DM Reply Received",
                        color=discord.Color.blue(),
                        timestamp=message.created_at
                    )
                    
                    user_info = (
                        f"{message.author.mention}\n"
                        f"`{message.author.display_name}` "
                        f"({message.author.id})"
                    )
                    embed.add_field(
                        name="� User",
                        value=user_info,
                        inline=True
                    )
                    
                    content = message.content[:1024]
                    if len(message.content) > 1024:
                        content += "..."
                    if not content:
                        content = "*No text content*"
                    
                    embed.add_field(
                        name="📝 Message",
                        value=content,
                        inline=False
                    )
                    
                    # Add attachment info if any
                    if message.attachments:
                        attachment_list = [
                            f"📎 {att.filename}"
                            for att in message.attachments[:5]
                        ]
                        attachment_info = "\n".join(attachment_list)
                        if len(message.attachments) > 5:
                            extra_count = len(message.attachments) - 5
                            attachment_info += f"\n... and {extra_count} more"
                        embed.add_field(
                            name="📎 Attachments",
                            value=attachment_info,
                            inline=False
                        )
                    
                    embed.set_thumbnail(url=message.author.display_avatar.url)
                    embed.set_footer(text="DM Reply • Bot Logging System")
                    
                    try:
                        await log_channel.send(embed=embed)
                        break  # Only send to first available log channel
                    except discord.Forbidden:
                        continue  # Try next guild if no permission
                    except Exception as e:
                        self.logger.error(
                            "Failed to send DM log to %s: %s",
                            log_channel.name,
                            e
                        )
                        continue
                        
        except Exception as e:
            self.logger.error("Failed to log DM reply: %s", e)

    # ---------- mod whitelist persistence helpers ----------
    def load_mod_whitelist(self) -> None:
        try:
            if not os.path.exists(self.MOD_FILE):
                self.mod_whitelist = {}
                self.save_mod_whitelist()
                self.logger.info("Created empty mod whitelist at %s", self.MOD_FILE)
                return

            with open(self.MOD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                fixed: Dict[str, List[int]] = {}
                for gid, roles in data.items():
                    fixed[str(gid)] = [int(r) for r in roles if isinstance(r, (int, str))]
                self.mod_whitelist = fixed
            self.logger.info("Loaded mod whitelist for %d guild(s)", len(self.mod_whitelist))
        except Exception as e:
            self.logger.error("Failed to load mod whitelist: %s", e)
            self.mod_whitelist = {}

    def save_mod_whitelist(self) -> None:
        try:
            with open(self.MOD_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mod_whitelist, f, indent=2)
        except Exception as e:
            self.logger.error("Failed to save mod whitelist: %s", e)

    # ---------- mod whitelist query/mutation APIs ----------
    def get_guild_mod_role_ids(self, guild_id: int) -> Set[int]:
        roles = self.mod_whitelist.get(str(guild_id))
        if roles:
            return set(int(r) for r in roles)
        return set(ALLOWED_ROLE_IDS)

    def add_guild_mod_role(self, guild_id: int, role_id: int) -> None:
        key = str(guild_id)
        self.mod_whitelist.setdefault(key, [])
        if int(role_id) not in self.mod_whitelist[key]:
            self.mod_whitelist[key].append(int(role_id))
            self.save_mod_whitelist()

    def remove_guild_mod_role(self, guild_id: int, role_id: int) -> bool:
        key = str(guild_id)
        if key not in self.mod_whitelist:
            return False
        before = len(self.mod_whitelist[key])
        self.mod_whitelist[key] = [int(r) for r in self.mod_whitelist[key] if int(r) != int(role_id)]
        removed = len(self.mod_whitelist[key]) != before
        if not self.mod_whitelist[key]:
            del self.mod_whitelist[key]
        if removed:
            self.save_mod_whitelist()
        return removed

    # ---------- Convenience aliases for shorter method names ----------
    def add_mod_role(self, guild_id: int, role_id: int) -> None:
        """Alias for add_guild_mod_role for convenience."""
        return self.add_guild_mod_role(guild_id, role_id)

    def remove_mod_role(self, guild_id: int, role_id: int) -> bool:
        """Alias for remove_guild_mod_role for convenience."""
        return self.remove_guild_mod_role(guild_id, role_id)

    # ---------- ALT whitelist persistence ----------
    def load_alt_whitelist(self) -> None:
        try:
            if not os.path.exists(self.ALT_FILE):
                self.alt_whitelist_users = {}
                self.alt_whitelist_roles = {}
                self.save_alt_whitelist()
                self.logger.info("Created empty alt whitelist at %s", self.ALT_FILE)
                return

            with open(self.ALT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}

            users_map: Dict[int, Set[int]] = {}
            roles_map: Dict[int, Set[int]] = {}
            for gid_str, payload in data.items():
                gid = int(gid_str)
                users = set(int(u) for u in payload.get("users", []))
                roles = set(int(r) for r in payload.get("roles", []))
                users_map[gid] = users
                roles_map[gid] = roles

            self.alt_whitelist_users = users_map
            self.alt_whitelist_roles = roles_map
            self.logger.info("Loaded alt whitelist for %d guild(s)", len(users_map))
        except Exception as e:
            self.logger.error("Failed to load alt whitelist: %s", e)
            self.alt_whitelist_users = {}
            self.alt_whitelist_roles = {}

    def save_alt_whitelist(self) -> None:
        try:
            out: Dict[str, Dict[str, List[int]]] = {}
            all_guilds = set(self.alt_whitelist_users) | set(self.alt_whitelist_roles)
            for gid in all_guilds:
                out[str(gid)] = {
                    "users": sorted(self.alt_whitelist_users.get(gid, set())),
                    "roles": sorted(self.alt_whitelist_roles.get(gid, set())),
                }
            with open(self.ALT_FILE, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2)
        except Exception as e:
            self.logger.error("Failed to save alt whitelist: %s", e)

    # ---------- ALT whitelist query/mutation APIs ----------
    def get_alt_users(self, guild_id: int) -> Set[int]:
        return set(self.alt_whitelist_users.get(guild_id, set()))

    def get_alt_roles(self, guild_id: int) -> Set[int]:
        return set(self.alt_whitelist_roles.get(guild_id, set()))

    def add_alt_user(self, guild_id: int, user_id: int) -> None:
        self.alt_whitelist_users.setdefault(guild_id, set()).add(int(user_id))
        self.save_alt_whitelist()

    def remove_alt_user(self, guild_id: int, user_id: int) -> bool:
        s = self.alt_whitelist_users.setdefault(guild_id, set())
        existed = int(user_id) in s
        s.discard(int(user_id))
        self.save_alt_whitelist()
        return existed

    def add_alt_role(self, guild_id: int, role_id: int) -> None:
        self.alt_whitelist_roles.setdefault(guild_id, set()).add(int(role_id))
        self.save_alt_whitelist()

    def remove_alt_role(self, guild_id: int, role_id: int) -> bool:
        s = self.alt_whitelist_roles.setdefault(guild_id, set())
        existed = int(role_id) in s
        s.discard(int(role_id))
        self.save_alt_whitelist()
        return existed

    # ---------- ALT helpers ----------
    def is_alt_whitelisted(self, member: discord.Member) -> bool:
        if not isinstance(member, discord.Member):
            return False
        gu = self.alt_whitelist_users.get(member.guild.id, set())
        gr = self.alt_whitelist_roles.get(member.guild.id, set())
        if member.id in gu:
            return True
        role_ids = {r.id for r in getattr(member, "roles", [])}
        return bool(role_ids & gr)

    def allow_alt(self, member: discord.Member) -> bool:
        if not isinstance(member, discord.Member):
            return False
        return (
            member.guild_permissions.administrator
            or member.guild_permissions.manage_guild
            or self.is_alt_whitelisted(member)
        )

    # ---------- global allow checks ----------
    def _member_has_allowed_role(self, member: discord.Member) -> bool:
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.administrator:
            return True
        allowed = self.get_guild_mod_role_ids(member.guild.id)
        return any(role.id in allowed for role in getattr(member, "roles", []))

    async def _prefix_role_gate(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            await ctx.send("❌ Sorry, commands can only be used in a server, not in DMs!")
            return False

        # Special: alt
        if ctx.command and ctx.command.name.lower() == "alt":
            if not isinstance(ctx.author, discord.Member) or not self.allow_alt(ctx.author):
                raise commands.CheckFailure("❌ You don't have permission to use this command.")
            return True

        # Others: admin or whitelisted role
        if not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("❌ You don't have permission to use this command.")
        if ctx.author.guild_permissions.administrator:
            return True
        if self._member_has_allowed_role(ctx.author):
            return True
        raise commands.CheckFailure("❌ You don't have permission to use this command.")

    async def setup_hook(self):
        self.logger.info("Bot setup hook called")

        # Load cogs
        for cog in ["cogs.utility", "cogs.admin", "cogs.moderation"]:
            try:
                await self.load_extension(cog)
                self.logger.info(f"Loaded {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load {cog}: {e}")

        # Optional small-guild chunk
        self._enable_chunk_guild = lambda guild: len(guild.members) < 50
        for guild in self.guilds:
            if not guild.chunked and self._enable_chunk_guild(guild):
                try:
                    await guild.chunk()
                except discord.HTTPException:
                    pass

        # Prefix commands: global gate
        self.add_check(self._prefix_role_gate)

        # Slash commands: global gate
        async def _check_interaction(interaction: discord.Interaction) -> bool:
            if not interaction.guild:
                await interaction.response.send_message("❌ Commands can only be used in a server.", ephemeral=True)
                return False

            cmd_name = interaction.command.name if interaction.command else None
            if cmd_name == "health":
                return True

            if cmd_name == "alt":
                if not isinstance(interaction.user, discord.Member) or not self.allow_alt(interaction.user):
                    await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
                    return False
                return True

            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
                return False

            if interaction.user.guild_permissions.administrator:
                return True

            if any(r.id in self.get_guild_mod_role_ids(interaction.guild.id) for r in interaction.user.roles):
                return True

            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return False
            
        self.tree.interaction_check = _check_interaction

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            self.last_sync_time = utcnow()
            self._did_tree_sync = True
            self.logger.info("Synced %d slash commands", len(synced))
        except Exception as e:
            self.logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        # Set start time for uptime calculation
        if not hasattr(self, 'start_time'):
            self.start_time = utcnow()
            
        if self.user:
            self.logger.info(f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"Connected to {len(self.guilds)} guilds")
        activity = discord.Activity(type=discord.ActivityType.watching, name="for rule violations")
        await self.change_presence(activity=activity, status=discord.Status.online)

    async def on_guild_join(self, guild: discord.Guild):
        self.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        try:
            await self.tree.sync(guild=guild)
            self.logger.info(f"Synced commands for guild: {guild.name}")
        except Exception as e:
            self.logger.error(f"Failed to sync commands for {guild.name}: {e}")

    async def on_guild_remove(self, guild: discord.Guild):
        self.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return
        self.logger.error(f"Command error in {getattr(ctx, 'command', None)}: {error}")

        try:
            if isinstance(error, commands.NoPrivateMessage):
                msg = "❌ This command can only be used in a server."
            elif isinstance(error, commands.CheckFailure):
                msg = "❌ You don't have permission to use this command."
            elif isinstance(error, commands.MissingPermissions):
                msg = "❌ You don't have permission to use this command."
            elif isinstance(error, commands.BotMissingPermissions):
                msg = "❌ I don't have the necessary permissions to execute this command."
            else:
                msg = "❌ An error occurred while executing the command."

            # Handle different types of contexts
            if hasattr(ctx, 'interaction') and ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg, delete_after=5)
                
        except Exception as e:
            self.logger.error(f"Error sending error message: {e}", exc_info=True)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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

    async def close(self):
        """Clean shutdown of the bot."""
        # Stop the keep-alive task
        if hasattr(self, 'keep_alive_task') and self.keep_alive_task.is_running():
            self.keep_alive_task.cancel()
            self.logger.info("Keep-alive task stopped")
        
        # Call the parent close method
        await super().close()
        self.logger.info("Bot shutdown completed")

    # ---------- /health (public) ----------
    @app_commands.command(name="health", description="Show bot health / status.")
    async def health(self, interaction: discord.Interaction):
        latency_ms = round(self.latency * 1000)
        guild_count = len(self.guilds)
        shard_info = (
            f"{self.shard_id + 1}/{self.shard_count}"
            if self.shard_id is not None and self.shard_count
            else "—"
        )

        delta = utcnow() - self.boot_time
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if minutes: parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        uptime_str = " ".join(parts)

        embed = discord.Embed(
            title="✅ Bot Health",
            color=discord.Color.green(),
            description="The bot is running and connected to Discord."
        )
        if self.user:
            embed.set_author(name=str(self.user), icon_url=self.user.display_avatar.url)

        embed.add_field(name="Latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Shard", value=shard_info, inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Started", value=format_dt(self.boot_time, style='F'), inline=True)
        if self.last_sync_time:
            embed.add_field(name="Last Slash Sync", value=format_dt(self.last_sync_time, style='R'), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)
