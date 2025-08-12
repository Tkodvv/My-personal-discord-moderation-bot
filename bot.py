"""
Discord Bot Main Class
Contains the main bot class with event handlers and cog loading.
"""

import logging
import json
import os
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Set
from discord.utils import utcnow, format_dt  # <-- added

# === OPTIONAL: Legacy global role IDs fallback ===
ALLOWED_ROLE_IDS = {
    1383421890403762286,
    1349191381310111824,
    1379755293797384202,
}

# Import cogs
from cogs.moderation import ModerationCog
from cogs.utility import UtilityCog
from cogs.admin import AdminCog


class DiscordBot(commands.Bot):
    """Main Discord bot class with slash command support and per-guild mod whitelist."""

    # ---------- persistence paths ----------
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    MOD_FILE = os.path.join(DATA_DIR, "mod_whitelist.json")
    ALT_FILE = os.path.join(DATA_DIR, "alt_whitelist.json")  # <--- NEW

    def __init__(self):
        """Initialize the bot with necessary intents and settings."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.moderation = True
        intents.presences = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

        self.logger = logging.getLogger(__name__)

        # health/uptime tracking
        self.boot_time = utcnow()
        self.last_sync_time = None

        # Per-guild whitelist storage: { "<guild_id>": [role_id, ...] }
        self.mod_whitelist: Dict[str, List[int]] = {}

        # --- alt whitelist (per-guild, persisted) ---
        # {guild_id: {user_ids}}, {guild_id: {role_ids}}
        self.alt_whitelist_users: Dict[int, Set[int]] = {}
        self.alt_whitelist_roles: Dict[int, Set[int]] = {}

        # Ensure data dir exists and load files now
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.load_mod_whitelist()
        self.load_alt_whitelist()  # <--- NEW

    # ---------- mod whitelist persistence helpers ----------
    def load_mod_whitelist(self) -> None:
        """Load mod whitelist JSON from disk (creates empty file if missing)."""
        try:
            if not os.path.exists(self.MOD_FILE):
                self.mod_whitelist = {}
                self.save_mod_whitelist()
                self.logger.info("Created empty mod whitelist at %s", self.MOD_FILE)
                return

            with open(self.MOD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                # normalize to list[int]
                fixed: Dict[str, List[int]] = {}
                for gid, roles in data.items():
                    fixed[str(gid)] = [int(r) for r in roles if isinstance(r, (int, str))]
                self.mod_whitelist = fixed
            self.logger.info("Loaded mod whitelist for %d guild(s)", len(self.mod_whitelist))
        except Exception as e:
            self.logger.error("Failed to load mod whitelist: %s", e)
            self.mod_whitelist = {}

    def save_mod_whitelist(self) -> None:
        """Save current mod whitelist to disk."""
        try:
            with open(self.MOD_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mod_whitelist, f, indent=2)
        except Exception as e:
            self.logger.error("Failed to save mod whitelist: %s", e)

    # ---------- mod whitelist query/mutation APIs (restored) ----------
    def get_guild_mod_role_ids(self, guild_id: int) -> Set[int]:
        """
        Return the set of mod role IDs for a guild.
        If none stored for this guild, fallback to ALLOWED_ROLE_IDS.
        """
        roles = self.mod_whitelist.get(str(guild_id))
        if roles:
            return set(int(r) for r in roles)
        return set(ALLOWED_ROLE_IDS)

    def add_guild_mod_role(self, guild_id: int, role_id: int) -> None:
        """Add a role to the guild's whitelist and persist."""
        key = str(guild_id)
        self.mod_whitelist.setdefault(key, [])
        if int(role_id) not in self.mod_whitelist[key]:
            self.mod_whitelist[key].append(int(role_id))
            self.save_mod_whitelist()

    def remove_guild_mod_role(self, guild_id: int, role_id: int) -> bool:
        """Remove a role from the guild's whitelist and persist. Returns True if removed."""
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

    # ---------- ALT whitelist persistence (NEW) ----------
    def load_alt_whitelist(self) -> None:
        """Load alt whitelist mapping from disk."""
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
        """Persist alt whitelist to disk."""
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

    # ---------- ALT whitelist query/mutation APIs (NEW) ----------
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

    # ---------- ALT whitelist helpers ----------
    def is_alt_whitelisted(self, member: discord.Member) -> bool:
        """True if member is explicitly whitelisted for /alt via user or role."""
        if not isinstance(member, discord.Member):
            return False
        gu = self.alt_whitelist_users.get(member.guild.id, set())
        gr = self.alt_whitelist_roles.get(member.guild.id, set())
        if member.id in gu:
            return True
        role_ids = {r.id for r in getattr(member, "roles", [])}
        return bool(role_ids & gr)

    def allow_alt(self, member: discord.Member) -> bool:
        """Staff or explicitly whitelisted can use /alt."""
        if not isinstance(member, discord.Member):
            return False
        return (
            member.guild_permissions.administrator
            or member.guild_permissions.manage_guild
            or self.is_alt_whitelisted(member)
        )

    # ---------- global allow checks ----------
    def _member_has_allowed_role(self, member: discord.Member) -> bool:
        """True if member is admin or has a role in this guild's whitelist (or fallback)."""
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.administrator:
            return True
        allowed = self.get_guild_mod_role_ids(member.guild.id)
        return any(role.id in allowed for role in getattr(member, "roles", []))

    async def _prefix_role_gate(self, ctx: commands.Context) -> bool:
        """
        Global check for ALL prefix commands.
        Return False (and raise CheckFailure) if blocked.
        """
        if ctx.guild is None:
            raise commands.CheckFailure("❌ Commands can only be used in a server.")

        # allow whitelisted users to use !alt even if they aren't in mod roles
        if ctx.command and ctx.command.name and ctx.command.name.lower() == "alt":
            author = ctx.author if isinstance(ctx.author, discord.Member) else None
            if author and self.allow_alt(author):
                return True

        author = ctx.author
        if not isinstance(author, discord.Member) or not self._member_has_allowed_role(author):
            raise commands.CheckFailure("❌ You don’t have access to use bot commands here.")
        return True

    async def setup_hook(self):
        """Called when the bot is starting up. Load cogs and sync commands."""
        self.logger.info("Bot setup hook called")

        # Prefix commands: global gate
        self.add_check(self._prefix_role_gate)

        # Slash commands: global gate
        @self.tree.interaction_check
        async def _global_slash_gate(interaction: discord.Interaction) -> bool:
            # allow /health for everyone so you can always check status
            if interaction.command and interaction.command.name == "health":
                return True

            if interaction.guild is None:
                try:
                    await interaction.response.send_message("❌ Commands can only be used in a server.", ephemeral=True)
                finally:
                    return False

            # --- special case: /alt — allow if the member is whitelisted for alt; else say why ---
            cmd_name = ""
            try:
                if interaction.command:
                    cmd_name = (interaction.command.qualified_name or interaction.command.name or "").lower()
            except Exception:
                pass

            if cmd_name.split(" ")[0] == "alt":
                member = interaction.user if isinstance(interaction.user, discord.Member) \
                         else interaction.guild.get_member(interaction.user.id)
                if member and self.allow_alt(member):
                    return True  # ✅ bypass gate for /alt
                # explicit fallback message for /alt
                try:
                    await interaction.response.send_message(
                        "❌ You’re not whitelisted to use `/alt` here. Ask a staff member to add you.",
                        ephemeral=True
                    )
                except discord.InteractionResponded:
                    await interaction.followup.send(
                        "❌ You’re not whitelisted to use `/alt` here. Ask a staff member to add you.",
                        ephemeral=True
                    )
                return False

            # --- normal global gate for everything else ---
            user = interaction.user
            if isinstance(user, discord.Member):
                if user.guild_permissions.administrator:
                    return True
                if any(r.id in self.get_guild_mod_role_ids(interaction.guild.id) for r in user.roles):
                    return True

            try:
                await interaction.response.send_message("❌ You don’t have access to use bot commands here.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("❌ You don’t have access to use bot commands here.", ephemeral=True)
            return False

        # Add cogs
        await self.add_cog(ModerationCog(self))
        await self.add_cog(UtilityCog(self))
        await self.add_cog(AdminCog(self))

        self.logger.info("All cogs loaded successfully")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            self.last_sync_time = utcnow()
            self.logger.info("Synced %d slash commands", len(synced))
        except Exception as e:
            self.logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        if self.user:
            self.logger.info(f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"Connected to {len(self.guilds)} guilds")

        activity = discord.Activity(type=discord.ActivityType.watching, name="for rule violations")
        await self.change_presence(activity=activity, status=discord.Status.online)

    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild."""
        self.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        try:
            await self.tree.sync(guild=guild)
            self.logger.info(f"Synced commands for guild: {guild.name}")
        except Exception as e:
            self.logger.error(f"Failed to sync commands for {guild.name}: {e}")

    async def on_guild_remove(self, guild):
        """Called when the bot leaves a guild."""
        self.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")

    async def on_command_error(self, ctx, error):
        """Handle command errors for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return
        self.logger.error(f"Command error in {getattr(ctx, 'command', None)}: {error}")

        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don’t have access to use bot commands here.", delete_after=5)
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the necessary permissions to execute this command.")
        else:
            await ctx.send("❌ An error occurred while executing the command.")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle slash command errors."""
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

    # ---------- /health (public) ----------
    @app_commands.command(name="health", description="Show bot health / status.")
    async def health(self, interaction: discord.Interaction):
        """Public health check: latency, uptime, guild/shard counts, last sync."""
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
