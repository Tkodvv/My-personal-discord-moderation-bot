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
from typing import Optional, Dict
from discord.utils import utcnow, format_dt

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

        # Allowed roles for /say (you can remove this if you want to fully rely on modlist)
        self.allowed_say_roles = {
            1383421890403762286,
            1349191381310111824,
            1379755293797384202,
        }

        # Global "no ping" policy for safe responses
        self.no_pings = discord.AllowedMentions.none()

        # Env-driven blacklist
        self.guild_blacklist: set[int] = _parse_guild_blacklist_from_env()

    # ===== ALT role whitelist helpers (robust) =====
    def _get_alt_role_ids(self, guild_id: int) -> set[int]:
        """Return role IDs allowed to use /alt in a guild."""
        # Prefer persistent method if it returns usable data
        if hasattr(self.bot, "get_alt_role_ids"):
            try:
                data = self.bot.get_alt_role_ids(guild_id)
                if data:  # only trust if not None/empty
                    return set(data)
            except Exception:
                pass
        # Fallback to in-memory store on the bot object
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        return set(store.get(guild_id, set()))

    def _add_alt_role(self, guild_id: int, role_id: int) -> None:
        """Add a role to the whitelist, persisting if possible and always keeping a fallback copy."""
        persisted = False
        if hasattr(self.bot, "add_alt_role"):
            try:
                res = self.bot.add_alt_role(guild_id, role_id)
                if res is not False:
                    persisted = True
            except Exception:
                persisted = False
        # Always ensure our in-memory fallback is updated too
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        store.setdefault(guild_id, set()).add(role_id)

    def _remove_alt_role(self, guild_id: int, role_id: int) -> bool:
        """Remove a role from the whitelist (persistent + fallback)."""
        removed = False
        if hasattr(self.bot, "remove_alt_role"):
            try:
                removed = bool(self.bot.remove_alt_role(guild_id, role_id))
            except Exception:
                removed = False
        # Also remove from fallback
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store and guild_id in store and role_id in store[guild_id]:
            store[guild_id].remove(role_id)
            removed = True or removed
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
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

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
        # Sweep any already-joined blacklisted guilds
        for g in list(self.bot.guilds):
            if g.id in self.guild_blacklist:
                try:
                    await g.leave()
                    self.logger.info(f"Left blacklisted guild on_ready: {g.name} ({g.id})")
                except Exception as e:
                    self.logger.error(f"Failed to leave blacklisted guild on_ready {g.id}: {e}")

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
        # Block slash commands in DMs (extra safety on top of @app_commands.guild_only())
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

        # Block in blacklisted guilds
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
        import datetime as dt

        enabled = os.getenv("MOD_ENABLE_RBX_ALT", "false").lower() in {"1","true","yes","y"}
        show_pw = os.getenv("ALT_SHOW_PASSWORD", "true").lower() in {"1","true","yes","y"}
        is_slash = getattr(ctx, "interaction", None) is not None

        async def _slash_reply(msg: str, *, ephemeral: bool = True):
            """Safe reply helper for slash branch."""
            if not is_slash:
                return
            try:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(msg, ephemeral=ephemeral)
                else:
                    await ctx.interaction.followup.send(msg, ephemeral=ephemeral)
            except Exception:
                pass

        if not enabled:
            return await _slash_reply("alts feature is disabled.") if is_slash else await ctx.send("alts feature is disabled.")

        member = ctx.author if isinstance(ctx.author, discord.Member) else None
        # allow either user-whitelisted OR role-whitelisted
        if not (member and (self.bot.allow_alt(member) or self._member_has_alt_role(member))):
            return await _slash_reply("❌ You’re not allowed to use `/alt` in this server.", ephemeral=True) \
                   if is_slash else await ctx.send("❌ You’re not allowed to use `!alt` in this server.", delete_after=5)

        # For slash: defer NON-ephemeral so the final success message can be public
        if is_slash:
            try:
                await ctx.interaction.response.defer()  # not ephemeral
            except Exception:
                pass

        try:
            prof = await get_alt_public()
            if not prof or not prof.get("username"):
                if is_slash:
                    await ctx.interaction.followup.send("❌ couldn't fetch a random alt rn, try again later.")
                else:
                    await ctx.send("❌ couldn't fetch a random alt rn, try again later.", delete_after=6)
                return

            username = (prof.get("username") or "").strip()
            password = (prof.get("password") or "").strip()
            user_id  = str(prof.get("userId") or "")
            created_raw = prof.get("createdAt") or ""
            avatar_url  = prof.get("avatarUrl")

            # parse creation date into M/D/YYYY if possible
            creation_date = None
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    creation_date = dt.datetime.strptime(created_raw, fmt).strftime("%-m/%-d/%Y")
                    break
                except Exception:
                    pass
            if not creation_date and created_raw:
                creation_date = str(created_raw)

            embed = discord.Embed(
                title="Generated Roblox Account",
                description="Your account has been generated successfully! Keep it safe and **do not share it with anyone.**",
                color=discord.Color.red()
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            embed.add_field(name="Username", value=f"`{username}`", inline=False)
            if show_pw and password:
                embed.add_field(name="Password", value=f"`{password}`", inline=False)
            if user_id:
                embed.add_field(name="User ID", value=f"`{user_id}`", inline=False)
            if creation_date:
                embed.add_field(name="Creation Date", value=f"`{creation_date}`", inline=False)
            embed.set_footer(text="You must change the password to keep the account!")

            # Always DM the credentials
            try:
                await ctx.author.send(embed=embed)
            except discord.Forbidden:
                if is_slash:
                    await ctx.interaction.followup.send(
                        "❌ I couldn't DM you. Please enable DMs from server members and try again."
                    )
                else:
                    await ctx.send(
                        "❌ I couldn't DM you. Please enable DMs from server members and try again.",
                        delete_after=8
                    )
                return

            # Success confirmation (public for slash, short notice for prefix)
            success_msg = "✅ Account successfully generated — details have been sent to your direct messages."
            if is_slash:
                await ctx.interaction.followup.send(success_msg)  # NOT ephemeral
            else:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
                try:
                    await ctx.send(success_msg, delete_after=5)
                except Exception:
                    pass

        except commands.CommandOnCooldown as e:
            msg = f"slow down — try again in {e.retry_after:.1f}s"
            return await _slash_reply(msg, ephemeral=True) if is_slash else await ctx.send(msg)
        except Exception as e:
            self.logger.error("alt command failed: %s", e)
            return await _slash_reply("couldn't fetch a random alt rn, try again later.", ephemeral=True) \
                   if is_slash else await ctx.send("couldn't fetch a random alt rn, try again later.")

    # =========================================================
    # Alt Whitelist (slash) — uses bot's PERSISTENT storage
    # =========================================================
    @app_commands.command(name="alt_whitelist_add", description="Whitelist a user to use /alt without Manage Server.")
    @app_commands.describe(user="User to whitelist")
    @app_commands.guild_only()
    async def alt_whitelist_add(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        self.bot.add_alt_user(interaction.guild.id, user.id)
        await interaction.response.send_message(
            f"✅ {user.mention} whitelisted for /alt.",
            allowed_mentions=self.no_pings
        )

    @app_commands.command(name="alt_whitelist_remove", description="Remove a user from the /alt whitelist.")
    @app_commands.describe(user="User to remove")
    @app_commands.guild_only()
    async def alt_whitelist_remove(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        removed = self.bot.remove_alt_user(interaction.guild.id, user.id)
        msg = f"✅ Removed {user.mention} from whitelist." if removed else f"ℹ️ {user.mention} wasn’t whitelisted."
        await interaction.response.send_message(msg, allowed_mentions=self.no_pings)

    @app_commands.command(name="alt_whitelist_list", description="Show users whitelisted for /alt in this server.")
    @app_commands.guild_only()
    async def alt_whitelist_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        ids = sorted(self.bot.get_alt_users(interaction.guild.id))
        if not ids:
            await interaction.response.send_message("No users are whitelisted.")
            return
        mentions = []
        for uid in ids:
            u = interaction.guild.get_member(uid) or await interaction.client.fetch_user(uid)
            mentions.append(u.mention if u else f"<@{uid}>")
        await interaction.response.send_message(
            "Whitelisted: " + ", ".join(mentions),
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
            allowed_mentions=self.no_pings
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
        await interaction.response.send_message(msg, allowed_mentions=self.no_pings)

    @app_commands.command(
        name="alt_whitelist_role_list",
        description="Show ROLES whitelisted for /alt in this server."
    )
    @app_commands.guild_only()
    async def alt_whitelist_role_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** to use this.", ephemeral=True)
            return
        ids = sorted(self._get_alt_role_ids(interaction.guild.id))
        if not ids:
            await interaction.response.send_message("No roles are whitelisted.")
            return
        mentions = []
        for rid in ids:
            r = interaction.guild.get_role(rid)
            mentions.append(r.mention if r else f"<@&{rid}>")
        await interaction.response.send_message(
            "Role-whitelisted for /alt: " + ", ".join(mentions),
            allowed_mentions=self.no_pings
        )

    # =========================================================
    # Owner-only: Force the bot to leave a server (GUILD-ONLY)
    # =========================================================
    @app_commands.command(name="force_leave", description="(Owner only) Make the bot leave a server.")
    @app_commands.describe(guild_id="Guild ID to leave (default: the current server)")
    @app_commands.guild_only()
    async def force_leave(self, interaction: discord.Interaction, guild_id: Optional[str] = None):
        # Restrict to app owner
        try:
            is_owner = await self.bot.is_owner(interaction.user)
        except Exception:
            is_owner = False

        if not is_owner:
            await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
            return

        # Determine target guild (by ID or current)
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
    @app_commands.command(name="sync_commands", description="(Owner only) Sync slash commands now.")
    @app_commands.guild_only()
    async def sync_commands(self, interaction: discord.Interaction):
        try:
            is_owner = await self.bot.is_owner(interaction.user)
        except Exception:
            is_owner = False
        if not is_owner:
            await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"✅ Synced **{len(synced)}** command(s).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    # =========================================================
    # Owner-only: Reload blacklist from env
    # =========================================================
    @app_commands.command(name="reload_blacklist", description="(Owner only) Reload the guild blacklist from environment.")
    @app_commands.guild_only()
    async def reload_blacklist(self, interaction: discord.Interaction):
        try:
            is_owner = await self.bot.is_owner(interaction.user)
        except Exception:
            is_owner = False
        if not is_owner:
            await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
            return

        self.guild_blacklist = _parse_guild_blacklist_from_env()
        await interaction.response.send_message(
            f"✅ Blacklist reloaded. {len(self.guild_blacklist)} guild ID(s) configured.",
            ephemeral=True
        )

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
        await ctx.send(msg, delete_after=5, allowed_mentions=self.no_pings)

    @commands.command(name="modlist")
    @commands.has_permissions(manage_guild=True)
    async def p_modlist(self, ctx):
        await self.delete_command_message(ctx)
        ids = self.bot.get_guild_mod_role_ids(ctx.guild.id)
        mentions = [r.mention for r in (ctx.guild.get_role(i) for i in ids) if r]
        text = ", ".join(mentions) if mentions else "_(none)_"
        await ctx.send("**Mod roles:** " + text, delete_after=10, allowed_mentions=self.no_pings)

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
            # keep /say behavior unchanged – you can still ping if you type a mention
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

        await interaction.response.send_message(embed=embed)

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
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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

            await interaction.response.send_message(embed=embed, allowed_mentions=self.no_pings)
            self.logger.info(f"Nickname changed for {member} by {interaction.user}: {old_nick} -> {nickname or member.name}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to change this member's nickname.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to change nickname: {e}", ephemeral=True)

    @app_commands.command(name="addrole", description="Add a role to a member")
    @app_commands.describe(member="The member to add the role to", role="The role to add")
    @app_commands.guild_only()
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
            await interaction.response.send_message(embed=embed, allowed_mentions=self.no_pings)
            self.logger.info(f"Role {role.name} added to {member} by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to add this role.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to add role: {e}", ephemeral=True)

    @app_commands.command(name="watchuser", description="Add a user to the watch list for monitoring")
    @app_commands.describe(user="The user to add to watch list", reason="Reason for watching this user")
    @app_commands.guild_only()
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

        await interaction.response.send_message(embed=embed, allowed_mentions=self.no_pings)
        self.logger.info(f"User {user} added to watch list by {interaction.user} - Reason: {reason}")

    # =========================
    # Prefix command versions
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
        # No further confirmation (we just left)

    @commands.command(name="synccommands")
    @commands.is_owner()
    async def prefix_synccommands(self, ctx: commands.Context):
        await self.delete_command_message(ctx)
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Synced **{len(synced)}** command(s).", delete_after=6)
        except Exception as e:
            await ctx.send(f"❌ Sync failed: {e}", delete_after=8)

async def setup(bot):
    """Setup function for the cog."""
    cog = AdminCog(bot)
    await bot.add_cog(cog)

    # Global blacklist checks (apply once here):
    # - Slash commands: block in blacklisted guilds and in DMs
    # - Prefix commands: block in blacklisted guilds
    try:
        bot.tree.add_check(cog._interaction_not_blacklisted)
    except Exception as e:
        cog.logger.error(f"Failed to add app command blacklist check: {e}")

    try:
        bot.add_check(cog._prefix_not_blacklisted)
    except Exception as e:
        cog.logger.error(f"Failed to add prefix blacklist check: {e}")
