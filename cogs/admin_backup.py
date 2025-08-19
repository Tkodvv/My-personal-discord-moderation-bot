"""
Admin Cog
Contains administrative commands like say, announce, clear, prefix management,
and per-guild bot-mod role management (persistent). Also includes /alt with whitelist.
"""

import logging
import io
import os
import httpx
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional, Dict, List, Set
from discord.utils import utcnow, format_dt
from roblox_alts import get_alt_public

log = logging.getLogger(__name__)

# ---------------------------
# Inline Roblox Alt API client
# Defaults: POST + x-api-key to https://trigen.io/api/alt/generate
# ---------------------------
async def get_alt_public():
    API_KEY  = os.getenv("TRIGEN_API_KEY")
    API_BASE = (os.getenv("TRIGEN_BASE", "https://trigen.io") or "").rstrip("/")
    ENDPOINT = os.getenv("TRIGEN_ALT_ENDPOINT", "/api/alt/generate")
    METHOD   = os.getenv("TRIGEN_METHOD", "POST").upper()
    if not API_KEY:
        raise RuntimeError("TRIGEN_API_KEY missing")

    url = f"{API_BASE}{ENDPOINT}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "SliceMod/1.0",
        "x-api-key": API_KEY,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.request(METHOD, url, headers=headers)
        if r.status_code in (404, 405):
            fallback = "GET" if METHOD == "POST" else "POST"
            r = await client.request(fallback, url, headers=headers)

        r.raise_for_status()
        data = r.json()

    username = (data.get("username") or data.get("name") or data.get("user") or "").strip()
    password = (data.get("password") or data.get("pass") or data.get("pwd") or "").strip()
    user_id  = str(data.get("userId") or data.get("id") or data.get("userid") or "")

    created_raw = (
        data.get("createdAt") or data.get("creationDate") or
        data.get("created_at") or data.get("created") or ""
    )
    avatar_url = data.get("avatarUrl") or data.get("avatar_url")

    core = {"username","name","user","password","pass","pwd","userId","id","userid",
            "createdAt","creationDate","created_at","created","avatarUrl","avatar_url"}
    meta = {k: v for k, v in data.items() if k not in core}

    return {
        "username": username,
        "password": password,
        "userId": user_id,
        "createdAt": created_raw,
        "avatarUrl": avatar_url,
        "meta": meta,
    }

# ---------------------------
# Env-driven guild blacklist helper
# ---------------------------
def _parse_guild_blacklist_from_env() -> set[int]:
    raw = os.getenv("GUILD_BLACKLIST", "") or ""
    parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    ids: set[int] = set()
    for p in parts:
        try:
            ids.add(int(p))
        except ValueError:
            pass
    return ids

class AdminCog(commands.Cog):
    """Administrative commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.deleted_messages: Dict[int, dict] = {}
        self._last_deleted = {}
        self._watching_users = set()
        self.guild_blacklist = set()  # Initialize empty blacklist
        
        # Initialize storage
        store = {}
        if hasattr(bot, "alt_whitelist_roles"):
            for guild_id, roles in bot.alt_whitelist_roles.items():
                store[int(guild_id)] = set(int(r) for r in roles)
        setattr(bot, "_alt_role_whitelist", store)
        
        # Allowed roles for /say (you can remove this if you want to fully rely on modlist)
        self.allowed_say_roles = {
            1383421890403762286,
            1349191381310111824,
            1379755293797384202,
        }

        # Global "no ping" policy for safe responses
        self.no_pings = discord.AllowedMentions.none()
            
    @commands.command(name="prefix", aliases=["setprefix"])
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx, *, new_prefix: Optional[str] = None):
        """
        !prefix -> show current prefix
        !prefix <new> -> set new prefix (preserves mention as prefix)
        """
        await self.delete_command_message(ctx)
        if new_prefix is None or new_prefix == "?":
            current = getattr(self.bot, "command_prefix", "!")
            current = current if isinstance(current, str) else "!"
            await ctx.send(f"Current prefix is: `{current}`", delete_after=5)
            return
            
        if len(new_prefix) > 5:
            await ctx.send("❌ Prefix must be 5 characters or less", delete_after=5)
            return
            
        def get_prefix(bot, msg):
            return commands.when_mentioned_or(new_prefix)(bot, msg)
            
        self.bot.command_prefix = get_prefix
        await ctx.send(f"✅ Prefix updated to: `{new_prefix}`", delete_after=5)
        
    # Note: Removed duplicate prefix commands

        # Env-driven blacklist
        self.guild_blacklist: set[int] = _parse_guild_blacklist_from_env()

    # ===== Helpers: prefix handling (persist current text prefix on bot) =====
    def _get_current_prefix(self) -> str:
        return getattr(self.bot, "_text_prefix", "!")

    def _apply_prefix(self, prefix: str) -> None:
        # Keep mention + prefix
        self.bot.command_prefix = commands.when_mentioned_or(prefix)
        setattr(self.bot, "_text_prefix", prefix)

    # ===== ALT role whitelist helpers (robust) =====
    def _get_alt_role_ids(self, guild_id: int) -> set[int]:
        """Return role IDs allowed to use /alt in a guild."""
        roles = set()
        if hasattr(self.bot, "get_alt_roles"):
            try:
                roles.update(self.bot.get_alt_roles(guild_id))
            except Exception as e:
                self.logger.error(f"Failed to get alt roles from persistent storage: {e}")
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        roles.update(store.get(guild_id, set()))
        return roles

    def _add_alt_role(self, guild_id: int, role_id: int) -> None:
        if hasattr(self.bot, "add_alt_role"):
            try:
                self.bot.add_alt_role(guild_id, role_id)
            except Exception:
                pass
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        store.setdefault(guild_id, set()).add(role_id)

    def _remove_alt_role(self, guild_id: int, role_id: int) -> bool:
        removed = False
        if hasattr(self.bot, "remove_alt_role"):
            try:
                removed = bool(self.bot.remove_alt_role(guild_id, role_id))
            except Exception:
                removed = False
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store and guild_id in store and role_id in store[guild_id]:
            store[guild_id].remove(role_id)
            removed = True
        return removed

    def _member_has_alt_role(self, member: discord.Member) -> bool:
        allowed_roles = self._get_alt_role_ids(member.guild.id)
        return any((r.id in allowed_roles) for r in member.roles)

    # (Optional) tiny helper to fetch guild by id
    def _g(self, gid: int) -> Optional[discord.Guild]:
        try:
            return self.bot.get_guild(int(gid))
        except Exception:
            return None

    async def delete_command_message(self, ctx):
        """Helper to delete command invocation messages."""
        # Don't try to delete interaction messages
        if isinstance(ctx, discord.Interaction):
            return
            
        try:
            if hasattr(ctx, 'message') and ctx.message:
                await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden, AttributeError) as e:
            self.logger.debug(f"Failed to delete command message: {e}")
        except Exception as e:
            self.logger.warning(f"Unexpected error deleting command message: {e}")

    # =========================================================
    # BLACKLIST: Auto-leave on join + sweep at startup
    # =========================================================
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if guild.id in self.guild_blacklist:
            try:
                await guild.leave()
                self.logger.info(f"Left blacklisted guild on join: {guild.name} ({guild.id})")
            except Exception as e:
                self.logger.error(f"Failed to leave blacklisted guild on join {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        # Log successful cog initialization
        self.logger.info(f"AdminCog ready in {len(self.bot.guilds)} guilds")

        # (Optional) first-run slash sync; harmless if you already sync elsewhere
        if not getattr(self.bot, "_did_tree_sync", False):
            try:
                await self.bot.tree.sync()
                self.bot._did_tree_sync = True
                self.logger.info("App commands globally synced.")
            except Exception as e:
                self.logger.error(f"Failed to sync app commands: {e}")

    # =========================================================
    # BLACKLIST: Global checks (slash & prefix)
    # =========================================================
    async def _interaction_not_blacklisted(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Slash commands can only be used in a server.",
                        ephemeral=True
                    )
            except Exception:
                pass
            return False

        gid = getattr(interaction.guild, "id", None)
        if gid and gid in self.guild_blacklist:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ This bot is not available in this server.",
                        ephemeral=True
                    )
            except Exception:
                pass
            return False

        return True

    async def _prefix_not_blacklisted(self, ctx: commands.Context) -> bool:
        gid = getattr(ctx.guild, "id", None)
        if gid and gid in self.guild_blacklist:
            await ctx.send("❌ This bot is not available in this server.", delete_after=8)
            return False
        return True

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        self.deleted_messages[message.channel.id] = {
            'content': message.content,
            'author': message.author,
            'created_at': message.created_at,
            'deleted_at': datetime.utcnow()
        }

    # =========================================================
    # HYBRID: /alt + !alt  (DM creds; Manage Server OR whitelisted; 5s cooldown)
    # =========================================================
    @commands.hybrid_command(name="alt", description="Generate a Roblox alt and DM the credentials to you.")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def alt(self, ctx: commands.Context):
        """Generate and DM a Roblox alt account."""
        if not os.getenv("MOD_ENABLE_RBX_ALT", "false").lower() in {"1", "true", "yes", "y"}:
            await ctx.send("❌ Alt generation is currently disabled.", ephemeral=True)
            return
        
        member = ctx.author if isinstance(ctx.author, discord.Member) else None
        if not (member and (self.bot.allow_alt(member) or self._member_has_alt_role(member))):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
            return

        # For slash commands, defer the response
        if ctx.interaction:
            await ctx.defer(ephemeral=True)

        try:
            alt_data = await get_alt_public()
            if not alt_data or not alt_data.get("username"):
                error_msg = "❌ Failed to generate alt account. Please try again later."
                await ctx.send(error_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title="Generated Roblox Account",
                description="Your account has been generated successfully! Keep it safe and **do not share** it with anyone.",
                color=0x2F3136
            )
            if username := alt_data.get("username"):
                embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
            if password := alt_data.get("password"):
                if os.getenv("ALT_SHOW_PASSWORD", "true").lower() in {"1", "true", "yes", "y"}:
                    embed.add_field(name="🔒 Password", value=f"`{password}`", inline=True)
            if user_id := alt_data.get("userId"):
                embed.add_field(name="🔢 User ID", value=f"`{user_id}`", inline=True)

            if created_at := alt_data.get("createdAt"):
                try:
                    date_formats = [
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                        "%Y-%m-%dT%H:%M:%SZ",
                        "%m/%d/%Y",
                        "%Y-%m-%d"
                    ]
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(created_at, fmt)
                            embed.add_field(name="📅 Creation Date", value=f"`{parsed_date.strftime('%m/%d/%Y')}`", inline=True)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            if avatar_url := alt_data.get("avatarUrl"):
                embed.set_thumbnail(url=avatar_url)

            embed.set_footer(text="⚠️ You must change the password to keep the account!")

            try:
                await ctx.author.send(embed=embed)
                public_embed = discord.Embed(
                    description=f"✅ Account details sent to {ctx.author.mention}'s DMs!",
                    color=discord.Color.green()
                )
                await ctx.send(embed=public_embed, ephemeral=True)
                        
            except discord.Forbidden:
                error_msg = "❌ I couldn't DM you. Please enable DMs from server members and try again."
                await ctx.send(error_msg, ephemeral=True)
                return

        except commands.CommandOnCooldown as e:
            cooldown_msg = f"⏰ Slow down! Try again in {e.retry_after:.1f}s"
            await ctx.send(cooldown_msg, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Alt generation failed: {e}")
            error_msg = "❌ An unexpected error occurred. Please try again later."
            await ctx.send(error_msg, ephemeral=True)

    # =========================================================
    # Alt Whitelist (slash) — uses bot's PERSISTENT storage
    # =========================================================
    @commands.hybrid_command(name="altwhitelist", description="Whitelist a user to use alt command without Manage Server")
    @app_commands.describe(user="User to whitelist")
    @commands.has_permissions(manage_guild=True)
    async def alt_whitelist_add(self, ctx: commands.Context, user: discord.User):
        """Whitelist a user to use alt command without Manage Server"""
        if not isinstance(ctx, discord.Interaction):
            await ctx.message.delete()
        self.bot.add_alt_user(ctx.guild.id, user.id)
        await ctx.send(f"✅ {user.mention} whitelisted for alt command.", allowed_mentions=self.no_pings)
    @app_commands.describe(user="User to whitelist")
    @app_commands.guild_only()
    async def alt_whitelist_add(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        self.bot.add_alt_user(interaction.guild.id, user.id)
        await interaction.response.send_message(
            f"✅ {user.mention} whitelisted for /alt.",
            allowed_mentions=self.no_pings,
            ephemeral=True
        )

    @commands.hybrid_command(name="altunwhitelist", description="Remove a user from the alt whitelist")
    @app_commands.describe(user="User to remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def alt_whitelist_remove(self, ctx: commands.Context, user: discord.User):
        """Remove a user from the alt whitelist"""
        if not isinstance(ctx, discord.Interaction):
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        removed = self.bot.remove_alt_user(ctx.guild.id, user.id)
        msg = f"✅ Removed {user.mention} from whitelist." if removed else f"ℹ️ {user.mention} wasn't whitelisted."
        await ctx.send(msg, allowed_mentions=self.no_pings, ephemeral=isinstance(ctx, discord.Interaction))
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        removed = self.bot.remove_alt_user(interaction.guild.id, user.id)
        msg = f"✅ Removed {user.mention} from whitelist." if removed else f"ℹ️ {user.mention} wasn’t whitelisted."
        await interaction.response.send_message(msg, allowed_mentions=self.no_pings, ephemeral=True)

    @commands.command(name="altwhitelisted")
    @commands.has_permissions(manage_guild=True)
    async def prefix_alt_whitelist_list(self, ctx):
        """Show users whitelisted for alt command"""
        await ctx.message.delete()
        ids = sorted(self.bot.get_alt_users(ctx.guild.id))
        if not ids:
            await ctx.send("No users are whitelisted.")
            return

        mentions = []
        for uid in ids:
            u = ctx.guild.get_member(uid) or await self.bot.fetch_user(uid)
            mentions.append(u.mention if u else f"<@{uid}>")

        await ctx.send("Whitelisted: " + ", ".join(mentions), allowed_mentions=self.no_pings)

    @app_commands.command(name="alt_whitelist_list", description="Show users whitelisted for /alt in this server.")
    @app_commands.guild_only()
    async def alt_whitelist_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        ids = sorted(self.bot.get_alt_users(interaction.guild.id))
        if not ids:
            await interaction.followup.send("No users are whitelisted.", ephemeral=True)
            return

        mentions = []
        for uid in ids:
            u = interaction.guild.get_member(uid) or await interaction.client.fetch_user(uid)
            mentions.append(u.mention if u else f"<@{uid}>")

        await interaction.followup.send(
            "Whitelisted: " + ", ".join(mentions),
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

    # =========================================================
    # Alt Whitelist (roles) — add / remove / list
    # =========================================================
    @app_commands.command(
        name="alt_whitelist_role_add",
        description="Whitelist a ROLE to use /alt without Manage Server."
    )
    @app_commands.describe(role="Role to whitelist")
    @app_commands.guild_only()
    async def alt_whitelist_role_add(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        self._add_alt_role(interaction.guild.id, role.id)
        await interaction.response.send_message(
            f"✅ {role.mention} whitelisted for /alt.",
            allowed_mentions=self.no_pings,
            ephemeral=True
        )

    @app_commands.command(
        name="alt_whitelist_role_remove",
        description="Remove a ROLE from the /alt whitelist."
    )
    @app_commands.describe(role="Role to remove")
    @app_commands.guild_only()
    async def alt_whitelist_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        removed = self._remove_alt_role(interaction.guild.id, role.id)
        msg = (f"✅ Removed {role.mention} from whitelist."
               if removed else f"ℹ️ {role.mention} wasn’t whitelisted.")
        await interaction.response.send_message(msg, allowed_mentions=self.no_pings, ephemeral=True)

    @app_commands.command(
        name="alt_whitelist_role_list",
        description="Show ROLES whitelisted for /alt in this server."
    )
    @app_commands.guild_only()
    async def alt_whitelist_role_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        ids = sorted(self._get_alt_role_ids(interaction.guild.id))
        if not ids:
            await interaction.followup.send("No roles are whitelisted.", ephemeral=True)
            return

        mentions = []
        for rid in ids:
            r = interaction.guild.get_role(rid)
            mentions.append(r.mention if r else f"<@&{rid}>")

        await interaction.followup.send(
            "Role-whitelisted for /alt: " + ", ".join(mentions),
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

    # =========================================================
    # Owner-only: Force the bot to leave a server (GUILD-ONLY)
    # =========================================================
    @commands.command(name="forceleave")
    @commands.is_owner()
    async def prefix_forceleave(self, ctx, guild_id: Optional[int] = None):
        """Make the bot leave a server"""
        await ctx.message.delete()
        
        target: Optional[discord.Guild] = None
        if guild_id:
            target = self.bot.get_guild(guild_id)
            if not target:
                await ctx.send("❌ I'm not in that server (or bad Guild ID).")
                return
        else:
            if not ctx.guild:
                await ctx.send("❌ No guild context; provide a Guild ID.")
                return
            target = ctx.guild

        name, gid = target.name, target.id
        try:
            await target.leave()
            self.logger.warning(f"Force-leave (prefix) by {ctx.author} for guild {name} ({gid})")
            await ctx.send(f"👋 Left **{name}** (`{gid}`).")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to leave that server (unexpected).")
        except Exception as e:
            await ctx.send(f"❌ Failed to leave: {e}")

    @app_commands.command(name="force_leave", description="(Owner only) Make the bot leave a server.")
    @app_commands.describe(guild_id="Guild ID to leave (default: the current server)")
    @app_commands.guild_only()
    async def force_leave(self, interaction: discord.Interaction, guild_id: Optional[str] = None):
        try:
            is_owner = await self.bot.is_owner(interaction.user)
        except Exception:
            is_owner = False

        if not is_owner:
            await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
            return

        target: Optional[discord.Guild] = None
        if guild_id:
            try:
                target = self.bot.get_guild(int(guild_id))
            except Exception:
                target = None
            if not target:
                await interaction.response.send_message("❌ I’m not in that server (or the Guild ID is invalid).", ephemeral=True)
                return
        else:
            target = interaction.guild
            if not target:
                await interaction.response.send_message("❌ No guild context; provide a Guild ID.", ephemeral=True)
                return

        name, gid = target.name, target.id
        await interaction.response.send_message(
            f"⚠️ Leaving **{name}** (`{gid}`).",
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

        try:
            await target.leave()
            self.logger.warning(f"Force-leave executed by {interaction.user} for guild {name} ({gid})")
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to leave that server (unexpected).", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to leave: {e}", ephemeral=True)
            return

        await interaction.followup.send(
            f"👋 Left **{name}** (`{gid}`).",
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

    # =========================================================
    # Owner-only: Sync slash commands (slash + prefix)
    # =========================================================
    @commands.hybrid_command(name="sync", description="(Owner only) Sync slash commands now")
    @commands.guild_only()
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context):
        """Sync slash commands"""
        if not isinstance(ctx, discord.Interaction):
            await ctx.message.delete()
        
        try:
            synced = await self.bot.tree.sync()
            msg = f"✅ Synced **{len(synced)}** command(s)."
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        except Exception as e:
            msg = f"❌ Sync failed: {e}"
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)

    # =========================================================
    # Owner-only: Reload blacklist from env
    # =========================================================
    @commands.hybrid_command(name="reloadblacklist", description="(Owner only) Reload the guild blacklist from environment")
    @commands.guild_only()
    @commands.is_owner()
    async def reload_blacklist(self, ctx: commands.Context):
        """Reload the guild blacklist from environment"""
        if not isinstance(ctx, discord.Interaction):
            await ctx.message.delete()
            
        try:
            self.guild_blacklist = _parse_guild_blacklist_from_env()
            msg = f"✅ Blacklist reloaded. {len(self.guild_blacklist)} guild ID(s) configured."
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        except Exception as e:
            msg = f"❌ Failed to reload blacklist: {e}"
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)

    # =========================================================
    # Bot modlist management (per-guild, persistent) – SLASH
    # =========================================================
    @app_commands.command(name="addmod", description="Add a role to this guild's bot-mod list (members with it can use the bot).")
    @app_commands.describe(role="Role to add")
    @app_commands.guild_only()
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
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

    @app_commands.command(name="removemod", description="Remove a role from this guild's bot-mod list.")
    @app_commands.describe(role="Role to remove")
    @app_commands.guild_only()
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
            ephemeral=True,
            allowed_mentions=self.no_pings
        )

    @app_commands.command(name="listmods", description="Show this guild's bot-mod roles.")
    @app_commands.guild_only()
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

        await interaction.response.send_message("\n".join(lines), ephemeral=True, allowed_mentions=self.no_pings)

    # =========================================================
    # Bot modlist management – PREFIX
    # =========================================================
    @commands.command(name="addmod")
    @commands.has_permissions(administrator=True)
    async def p_addmod(self, ctx, role: discord.Role):
        self.bot.add_guild_mod_role(ctx.guild.id, role.id)
        await self.delete_command_message(ctx)
        await ctx.send(f"✅ Added {role.mention} to the bot-mod list.", delete_after=5, allowed_mentions=self.no_pings)

    @commands.command(name="removemod")
    @commands.has_permissions(administrator=True)
    async def p_removemod(self, ctx, role: discord.Role):
        removed = self.bot.remove_guild_mod_role(ctx.guild.id, role.id)
        await self.delete_command_message(ctx)
        msg = "✅ Removed." if removed else "ℹ️ That role wasn’t on the list."
        await ctx.send(msg, delete_after=6, allowed_mentions=self.no_pings)

    @commands.command(name="modlist")
    @commands.has_permissions(manage_guild=True)
    async def p_modlist(self, ctx):
        await self.delete_command_message(ctx)
        ids = self.bot.get_guild_mod_role_ids(ctx.guild.id)
        mentions = [r.mention for r in (ctx.guild.get_role(i) for i in ids) if r]
        text = ", ".join(mentions) if mentions else "_(none)_"
        await ctx.send("**Mod roles:** " + text, delete_after=5, allowed_mentions=self.no_pings)

    # =========================
    # /say (text + attachments)
    # =========================
    @commands.command(name="say")
    async def prefix_say(self, ctx, *, message: str):
        """Make the bot say something (prefix version)"""
        if not isinstance(ctx.author, discord.Member):
            return
        
        # Check permissions
        has_role = any((role.id in self.allowed_say_roles) for role in ctx.author.roles)
        if not has_role:
            await ctx.message.delete()
            response = await ctx.send("❌ You don't have access to this command.")
            await response.delete(delay=5)
            return
            
        try:
            # Delete command message
            await ctx.message.delete()
            
            # Send the message
            allowed = discord.AllowedMentions(everyone=False, users=True, roles=True)
            await ctx.channel.send(content=message, allowed_mentions=allowed)
            self.logger.info(f"Say command used by {ctx.author} in {ctx.guild.name}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to send messages here.")
        except Exception as e:
            await ctx.send(f"❌ Failed to send: {e}")

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
    @app_commands.guild_only()
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
            allowed = discord.AllowedMentions(everyone=False, users=True, roles=True)
            await target.send(content=content, files=files or None, allowed_mentions=allowed)
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
    # /announce
    # =========================
    @commands.command(name="announce")
    @commands.has_permissions(manage_messages=True)
    async def prefix_announce(self, ctx, channel: Optional[discord.TextChannel] = None, *, message: str):
        """Send an announcement (prefix version)"""
        # Delete command message
        await ctx.message.delete()
        
        if not message.strip():
            response = await ctx.send("❌ Please provide an announcement message.")
            await response.delete(delay=5)
            return
        
        target = channel or ctx.channel
        
        try:
            # Create and send embed
            embed = discord.Embed(description=message.strip(), color=discord.Color.green())
            await target.send(embed=embed)
            
            # Send confirmation
            if target != ctx.channel:
                await ctx.send(f"✅ Announcement sent to {target.mention}")
            else:
                await ctx.send("✅ Announcement sent!")
            
        except discord.Forbidden:
            response = await ctx.send("❌ I don't have permission to send messages in that channel.")
            await response.delete(delay=5)
        except Exception as e:
            response = await ctx.send(f"❌ Failed to send announcement: {e}")
            await response.delete(delay=5)

    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(
        message="The announcement message (required)",
        title="Title of the announcement (optional)",
        channel="Channel to send the announcement to (optional)",
        ping_role="Role to ping above the embed (optional)"
    )
    @app_commands.guild_only()
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

        embed = discord.Embed(description=message, color=discord.Color.green())
        if title:
            embed.title = title

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

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def prefix_clear(self, ctx, amount: int, user: Optional[discord.Member] = None):
        """Clear messages from the channel (prefix version)"""
        # Delete command message
        await ctx.message.delete()
        
        if amount < 1 or amount > 100:
            response = await ctx.send("❌ Amount must be between 1 and 100.")
            await response.delete(delay=5)
            return

        try:
            if user:
                def check(message):
                    return message.author == user
                deleted = await ctx.channel.purge(limit=amount * 2, check=check)
                await ctx.send(f"✅ Deleted {len(deleted)} messages from {user.mention}")
            else:
                deleted = await ctx.channel.purge(limit=amount)
                await ctx.send(f"✅ Deleted {len(deleted)} messages")
            self.logger.info(f"Clear command used by {ctx.author} - deleted {len(deleted)} messages in {ctx.guild.name}")

        except discord.Forbidden:
            response = await ctx.send("❌ I don't have permission to delete messages.")
            await response.delete(delay=5)
        except discord.HTTPException as e:
            response = await ctx.send(f"❌ Failed to delete messages: {e}")
            await response.delete(delay=5)

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def prefix_clear(self, ctx, amount: int, user: Optional[discord.Member] = None):
        """Clear messages from the channel"""
        await ctx.message.delete()
        
        if amount < 1 or amount > 100:
            await ctx.send("❌ Amount must be between 1 and 100.")
            return

        try:
            if user:
                def check(message):
                    return message.author == user
                deleted = await ctx.channel.purge(limit=amount * 2, check=check)
                await ctx.send(f"✅ Deleted {len(deleted)} messages from {user.mention}")
            else:
                deleted = await ctx.channel.purge(limit=amount)
                await ctx.send(f"✅ Deleted {len(deleted)} messages")
            
            self.logger.info(f"Clear command used by {ctx.author} - deleted {len(deleted)} messages in {ctx.guild.name}")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to delete messages: {e}")

    @app_commands.command(name="clear", description="Clear messages from the channel")
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        user="Only delete messages from this user (optional)"
    )
    @app_commands.guild_only()
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
                await interaction.followup.send(
                    f"✅ Deleted {deleted_count} messages from {user.mention}",
                    ephemeral=True,
                    allowed_mentions=self.no_pings
                )
            else:
                deleted = await interaction.channel.purge(limit=amount)
                deleted_count = len(deleted)
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages", ephemeral=True)
            self.logger.info(f"Clear command used by {interaction.user} - deleted {deleted_count} messages in {interaction.guild.name}")

        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to delete messages: {e}", ephemeral=True)

    @commands.command(name="snipe")
    async def prefix_snipe(self, ctx):
        """Show the last deleted message in this channel (prefix version)"""
        # Delete command message
        await ctx.message.delete()
        
        channel_id = ctx.channel.id
        if channel_id not in self.deleted_messages:
            response = await ctx.send("❌ No recently deleted messages found in this channel.")
            await response.delete(delay=5)
            return
            
        deleted_msg = self.deleted_messages[channel_id]
        
        # Create embed
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
        
        # Send embed without auto-delete
        await ctx.send(embed=embed)

    @commands.command(name="snipe")
    async def prefix_snipe(self, ctx):
        """Show the last deleted message in this channel"""
        await ctx.message.delete()
        
        channel_id = ctx.channel.id
        if channel_id not in self.deleted_messages:
            await ctx.send("❌ No recently deleted messages found in this channel.")
            return
            
        deleted_msg = self.deleted_messages[channel_id]
        
        # Create embed
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
        
        await ctx.send(embed=embed)

    @app_commands.command(name="snipe", description="Show the last deleted message in this channel")
    @app_commands.guild_only()
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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================
    # PREFIX: classic commands (restored + auto-delete)
    # =========================================================
    @commands.command(name="say")
    async def prefix_say(self, ctx, *, message):
        await self.delete_command_message(ctx)
        if not isinstance(ctx.author, discord.Member):
            return
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ You don't have permission to use this command.", delete_after=6)
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
            await ctx.send(f"✅ Deleted {len(deleted)} messages", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.", delete_after=6)

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
        await ctx.send(embed=embed, delete_after=5)

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
            await ctx.send(f"✅ Direct message sent to {user.display_name}!", delete_after=5)
            self.logger.info(f"DM sent to {user} by {ctx.author} in {ctx.guild.name}: {message}")
        except discord.Forbidden:
            await ctx.send(f"❌ Could not send DM to {user.display_name}. They may have DMs disabled or blocked the bot.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to send DM: {e}", delete_after=5)
            self.logger.error(f"Failed to send DM to {user}: {e}")

    @commands.command(name="forceleave")
    @commands.is_owner()
    async def prefix_forceleave(self, ctx: commands.Context, guild_id: Optional[int] = None):
        await self.delete_command_message(ctx)
        target: Optional[discord.Guild] = None
        if guild_id:
            target = self.bot.get_guild(int(guild_id))
            if not target:
                await ctx.send("❌ I’m not in that server (or bad Guild ID).", delete_after=6)
                return
        else:
            if not ctx.guild:
                await ctx.send("❌ No guild context; provide a Guild ID.", delete_after=6)
                return
            target = ctx.guild

        name, gid = target.name, target.id
        try:
            await target.leave()
            self.logger.warning(f"Force-leave (prefix) by {ctx.author} for guild {name} ({gid})")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to leave that server (unexpected).", delete_after=6)
            return
        except Exception as e:
            await ctx.send(f"❌ Failed to leave: {e}", delete_after=8)
            return

    @commands.command(name="synccommands")
    @commands.is_owner()
    async def prefix_synccommands(self, ctx: commands.Context):
        await self.delete_command_message(ctx)
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Synced **{len(synced)}** command(s).", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Sync failed: {e}", delete_after=5)

    # ===== END OF ADMIN COG ====

async def setup(bot):
    await bot.add_cog(AdminCog(bot))

    @commands.command(name="announce")
    @commands.has_permissions(manage_messages=True)
    async def prefix_announce(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, ping_role: Optional[discord.Role] = None, *, message: str = ""):
        """
        Usage:
          !announce <#channel?> <@role?> <message>
        You can omit channel/role and just do: !announce Your message here
        """
        await self.delete_command_message(ctx)
        if not message.strip():
            await ctx.send("❌ Provide an announcement message.", delete_after=5)
            return

        target = channel or ctx.channel
        embed = discord.Embed(description=message.strip(), color=discord.Color.green())
        content = ping_role.mention if ping_role else None
        allowed = discord.AllowedMentions(everyone=False, users=True, roles=[ping_role] if ping_role else True)
        try:
            await target.send(content=content, embed=embed, allowed_mentions=allowed)
            note = f" (pinged {ping_role.mention})" if ping_role else ""
            await ctx.send(f"✅ Announcement sent to {target.mention}{note}", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to send messages there.", delete_after=6)

    @commands.command(name="setnick")
    @commands.has_permissions(manage_nicknames=True)
    async def prefix_setnick(self, ctx: commands.Context, member: discord.Member, *, nickname: Optional[str] = None):
        await self.delete_command_message(ctx)
        if member.top_role >= ctx.guild.me.top_role and member != ctx.guild.me:
            await ctx.send("❌ I cannot change this member's nickname due to role hierarchy.", delete_after=6)
            return
        try:
            old_nick = member.display_name
            await member.edit(nick=nickname)
            embed = discord.Embed(title="✅ Nickname Changed", color=discord.Color.green())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Old", value=old_nick, inline=True)
            embed.add_field(name="New", value=nickname or member.name, inline=True)
            embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
            embed.set_footer(text=f"Changed by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed, delete_after=10, allowed_mentions=self.no_pings)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change that nickname.", delete_after=6)

    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    async def prefix_addrole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        await self.delete_command_message(ctx)
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("❌ You cannot assign a role that is higher than or equal to your highest role.", delete_after=6)
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ I cannot assign this role due to role hierarchy.", delete_after=6)
            return
        if role in member.roles:
            await ctx.send(f"ℹ️ {member.display_name} already has the {role.name} role.", delete_after=6)
            return
        try:
            await member.add_roles(role)
            embed = discord.Embed(title="✅ Role Added", color=discord.Color.green())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Role Added", value=role.mention, inline=True)
            embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
            embed.set_footer(text=f"Added by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed, delete_after=10, allowed_mentions=self.no_pings)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to add that role.", delete_after=6)

    @commands.command(name="watchuser")
    @commands.has_permissions(kick_members=True)
    async def prefix_watchuser(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await self.delete_command_message(ctx)
        if not hasattr(self, 'watch_list'):
            self.watch_list = {}
        gid = ctx.guild.id
        self.watch_list.setdefault(gid, {})
        self.watch_list[gid][user.id] = {
            'user': user,
            'reason': reason,
            'added_by': ctx.author,
            'added_at': utcnow()
        }
        embed = discord.Embed(title="🕵️‍♂️ User Added to Watch List", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{user.mention} ({user.name}#{user.discriminator})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed, delete_after=12, allowed_mentions=self.no_pings)

    # =========================================================
    # Slash: Set prefix (keeps mention) — FIXED
    # =========================================================
    @commands.command(name="prefix", aliases=["setprefix"])
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx, *, prefix: str = None):
        """Change the bot's command prefix (prefix version)"""
        # Delete command message
        await ctx.message.delete()
        
        # Show current prefix if none provided
        if prefix is None:
            current = self.bot._text_prefix if hasattr(self.bot, '_text_prefix') else '!'
            response = await ctx.send(f"Current prefix is: `{current}`")
            await response.delete(delay=5)
            return
            
        # Check prefix length
        if len(prefix) > 5:
            response = await ctx.send("❌ Prefix must be 5 characters or less")
            await response.delete(delay=5)
            return
            
        # Update the bot's prefix
        self.bot.command_prefix = commands.when_mentioned_or(prefix)
        if hasattr(self.bot, '_text_prefix'):
            self.bot._text_prefix = prefix
            
        # Send confirmation
        await ctx.send(f"✅ Prefix updated to: `{prefix}`")

    @app_commands.command(name="setprefix", description="Change the bot's command prefix")
    @app_commands.describe(prefix="New prefix for the bot (max 5 characters)")
    @app_commands.guild_only()
    async def setprefix(self, interaction: discord.Interaction, prefix: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to change the prefix.", ephemeral=True)
            return

        if len(prefix) > 5:
            await interaction.response.send_message("❌ Prefix must be 5 characters or less.", ephemeral=True)
            return

        # Keep mention + prefix and remember text prefix
        self._apply_prefix(prefix)

        embed = discord.Embed(
            title="✅ Prefix Changed",
            description=f"Bot prefix has been changed to `{prefix}` (mention still works).",
            color=discord.Color.green()
        )
        embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
        embed.set_footer(text=f"Changed by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        self.logger.info(f"Prefix changed to '{prefix}' by {interaction.user} in {interaction.guild.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for the cog."""
    cog = AdminCog(bot)
    await bot.add_cog(cog)

    # Register the check directly on the commands instead
    for cmd in bot.tree.get_commands():
        # Some discord.py versions use app_commands checks; if this errors in your env, comment it out
        try:
            cmd.checks.append(cog._interaction_not_blacklisted)
        except Exception:
            pass
    
    try:
        bot.add_check(cog._prefix_not_blacklisted)
    except Exception as e:
        cog.logger.error(f"Failed to add prefix blacklist check: {e}")
