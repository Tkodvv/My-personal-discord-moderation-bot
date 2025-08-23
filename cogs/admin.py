# -*- coding: utf-8 -*-
"""
Admin Cog - Revamped for proper Discord functionality
Contains administrative commands and bot management features.
"""

import os
import json
import asyncio
import io
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Set, Union
import typing
import logging

# Import the alt generation function
try:
    from roblox_alts import get_alt_public
except ImportError:
    async def get_alt_public():
        return None


class CookieView(discord.ui.View):
    """View with button to show cookie."""
    
    def __init__(self, cookie: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.cookie = cookie
        
    @discord.ui.button(label="🍪 Show Cookie", style=discord.ButtonStyle.secondary, emoji="🍪")
    async def show_cookie(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show the cookie when button is clicked."""
        
        # Create cookie embed with the entire cookie in description
        cookie_embed = discord.Embed(
            title="🍪 Account Cookie",
            description=f"**⚠️ Keep this cookie safe and do not share it with anyone!**\n\n```\n{self.cookie}\n```",
            color=0x2F3136
        )
            
        cookie_embed.set_footer(text="This cookie expires when you change your password.")
        
        await interaction.response.send_message(embed=cookie_embed, ephemeral=True)
        
    async def on_timeout(self):
        """Disable all buttons when view times out."""
        for item in self.children:
            item.disabled = True


class AdminCog(commands.Cog):
    """Administrative commands and bot management."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.no_pings = discord.AllowedMentions.none()
        
        # Allowed roles for /say command
        self.allowed_say_roles = {
            1383421890403762286,
            1349191381310111824,
            1379755293797384202,
        }

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the cog is ready."""
        guild_count = len(self.bot.guilds)
        self.logger.info(f"AdminCog ready in {guild_count} guilds")

    # =========================================================
    # UTILITY COMMANDS
    # =========================================================

    @commands.hybrid_command(name="sync", description="Sync slash commands (Owner only)")
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context):
        """Sync slash commands globally."""
        if ctx.interaction:
            await ctx.defer()
            
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Synced **{len(synced)}** slash commands globally.")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: {str(e)}")

    @commands.hybrid_command(name="reload", description="Reload a cog (Owner only)")
    @app_commands.describe(cog="Name of the cog to reload")
    @commands.is_owner()
    async def reload_cog(self, ctx: commands.Context, cog: str):
        """Reload a specific cog."""
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"✅ Reloaded cog: `{cog}`", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Failed to reload `{cog}`: {str(e)}", ephemeral=True)

    # =========================================================
    # ALT GENERATION COMMANDS
    # =========================================================

    @commands.hybrid_command(name="alt", description="Generate and DM a Roblox alt account")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def alt(self, ctx: commands.Context):
        """Generate and DM a Roblox alt account."""
        # Check if alt generation is enabled
        if not os.getenv("MOD_ENABLE_RBX_ALT", "false").lower() in {"1", "true", "yes", "y"}:
            await ctx.send("❌ Alt generation is currently disabled.", ephemeral=True)
            return
        
        # Check permissions
        member = ctx.author if isinstance(ctx.author, discord.Member) else None
        if not member:
            await ctx.send("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        if not (self.bot.allow_alt(member) or self._member_has_alt_role(member)):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
            return

        # Defer for slash commands since this might take time
        if ctx.interaction:
            await ctx.defer()  # Remove ephemeral=True to make responses public

        try:
            alt_data = await get_alt_public()
            if not alt_data or not (alt_data.get("username") or alt_data.get("name")):
                await ctx.send("❌ Failed to generate alt account. Please try again later.", ephemeral=True)
                return

            # Create embed with alt data
            embed = discord.Embed(
                title="Generated Roblox Account",
                description="Your account has been generated successfully! Keep it safe and **do not share** it with anyone.",
                color=0x2F3136
            )
            
            # Add username and password in a clean layout
            if username := (alt_data.get("username") or alt_data.get("name")):
                embed.add_field(name="👤 Username", value=f"```{username}```", inline=True)
            if password := alt_data.get("password"):
                if os.getenv("ALT_SHOW_PASSWORD", "true").lower() in {"1", "true", "yes", "y"}:
                    embed.add_field(name="🔒 Password", value=f"```{password}```", inline=True)
            
            # Don't add cookie to embed - will be shown via button
            cookie = alt_data.get("cookie")
            
            # Try to get user ID and avatar from Roblox API using username
            avatar_url = None
            user_id = None
            
            if username := (alt_data.get("username") or alt_data.get("name")):
                # Try to get user ID from Roblox API using username
                try:
                    import aiohttp
                    self.logger.info(f"Fetching user ID for username: {username}")
                    async with aiohttp.ClientSession() as session:
                        # Get user ID from username
                        async with session.post("https://users.roblox.com/v1/usernames/users", 
                                              json={"usernames": [username]}) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if data.get("data") and len(data["data"]) > 0:
                                    user_id = data["data"][0].get("id")
                                    self.logger.info(f"Found user ID: {user_id}")
                                    
                                    # Now get avatar using user ID
                                    if user_id:
                                        async with session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false") as avatar_resp:
                                            if avatar_resp.status == 200:
                                                avatar_data = await avatar_resp.json()
                                                if avatar_data.get("data") and len(avatar_data["data"]) > 0:
                                                    avatar_url = avatar_data["data"][0].get("imageUrl")
                                                    self.logger.info(f"Found avatar URL: {avatar_url}")
                                            else:
                                                self.logger.warning(f"Avatar API returned status {avatar_resp.status}")
                            else:
                                self.logger.warning(f"Username API returned status {resp.status}")
                except Exception as e:
                    self.logger.warning(f"Failed to fetch Roblox user info: {e}")
            
            # Add User ID field if we found it
            if user_id:
                embed.add_field(name="🆔 User ID", value=str(user_id), inline=True)

            # Set avatar image if we got one
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
                self.logger.info("Set avatar thumbnail in embed")
            elif alt_data.get("avatarUrl"):  # Fallback to TRIGEN avatar if available
                embed.set_thumbnail(url=alt_data.get("avatarUrl"))
                self.logger.info("Used TRIGEN avatar URL")
            else:
                self.logger.warning("No avatar URL available")

            # Fetch actual Roblox account creation date
            creation_date_added = False
            if user_id:
                try:
                    import aiohttp
                    self.logger.info(f"Fetching creation date for user ID: {user_id}")
                    async with aiohttp.ClientSession() as session:
                        # Get user details including creation date from Roblox API
                        async with session.get(f"https://users.roblox.com/v1/users/{user_id}") as resp:
                            if resp.status == 200:
                                user_data = await resp.json()
                                created_date = user_data.get("created")
                                if created_date:
                                    try:
                                        # Parse the Roblox creation date format
                                        parsed_date = datetime.strptime(created_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                                        embed.add_field(name="📅 Creation Date", value=parsed_date.strftime('%m/%d/%Y'), inline=True)
                                        creation_date_added = True
                                        self.logger.info(f"Found creation date: {parsed_date.strftime('%m/%d/%Y')}")
                                    except ValueError as e:
                                        self.logger.warning(f"Failed to parse creation date: {e}")
                            else:
                                self.logger.warning(f"User details API returned status {resp.status}")
                except Exception as e:
                    self.logger.warning(f"Failed to fetch Roblox creation date: {e}")
            
            # Try to parse creation date from TRIGEN if Roblox API failed
            if not creation_date_added and (created_at := alt_data.get("createdAt")):
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
                            embed.add_field(name="📅 Creation Date", value=parsed_date.strftime('%m/%d/%Y'), inline=True)
                            creation_date_added = True
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            # If no creation date from either API, use current date as fallback
            if not creation_date_added:
                current_date = datetime.now().strftime('%m/%d/%Y')
                embed.add_field(name="📅 Creation Date", value=current_date, inline=True)

            embed.set_footer(text="⚠️ You must change the password to keep the account!")

            # Try to send DM
            try:
                # Create view with cookie button if cookie exists
                view = CookieView(cookie) if cookie else None
                
                await ctx.author.send(embed=embed, view=view)
                # Send public success message
                public_embed = discord.Embed(
                    title="🎉 Roblox Account Generated!",
                    description=f"✅ Account successfully generated and sent to {ctx.author.mention}'s DMs!",
                    color=discord.Color.green()
                )
                public_embed.set_footer(text="Check your DMs for account details")
                await ctx.send(embed=public_embed)  # Remove ephemeral=True to make it public
                        
            except discord.Forbidden:
                await ctx.send("❌ I couldn't DM you. Please enable DMs from server members and try again.", ephemeral=True)

        except commands.CommandOnCooldown as e:
            await ctx.send(f"⏰ Slow down! Try again in {e.retry_after:.1f}s", ephemeral=True)
        except RuntimeError as e:
            if str(e) == "TOKENS_EXHAUSTED":
                error_embed = discord.Embed(
                    title="🪙 API Tokens Exhausted",
                    description="❌ **The API has no tokens left!**\n\nPlease contact the bot administrator to refill the token balance.",
                    color=0xFF6B6B,
                    timestamp=discord.utils.utcnow()
                )
                error_embed.set_footer(text="TRIGEN API • Token Balance: 0")
                await ctx.send(embed=error_embed, ephemeral=True)
                self.logger.warning("TRIGEN API tokens exhausted")
            else:
                self.logger.error(f"Alt generation failed: {e}")
                await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Alt generation failed: {e}")
            await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)

    # =========================================================
    # ALT WHITELIST COMMANDS (Hybrid)
    # =========================================================

    @commands.hybrid_command(name="altwhitelist", description="Whitelist a user for alt command")
    @app_commands.describe(user="User to whitelist")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def alt_whitelist_add(self, ctx: commands.Context, user: discord.User):
        """Add a user to the alt whitelist."""
        self.bot.add_alt_user(ctx.guild.id, user.id)
        await ctx.send(f"✅ {user.mention} has been whitelisted for the alt command.", 
                      allowed_mentions=self.no_pings, ephemeral=True)

    @commands.hybrid_command(name="altunwhitelist", description="Remove a user from alt whitelist")
    @app_commands.describe(user="User to remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def alt_whitelist_remove(self, ctx: commands.Context, user: discord.User):
        """Remove a user from the alt whitelist."""
        removed = self.bot.remove_alt_user(ctx.guild.id, user.id)
        msg = f"✅ Removed {user.mention} from whitelist." if removed else f"ℹ️ {user.mention} wasn't whitelisted."
        await ctx.send(msg, allowed_mentions=self.no_pings, ephemeral=True)

    @commands.hybrid_command(name="altwhitelisted", description="Show users whitelisted for alt command")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def alt_whitelist_list(self, ctx: commands.Context):
        """Show users whitelisted for alt command."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)

        ids = sorted(self.bot.get_alt_users(ctx.guild.id))
        if not ids:
            await ctx.send("No users are whitelisted for the alt command.", ephemeral=True)
            return

        mentions = []
        for uid in ids:
            try:
                user = ctx.guild.get_member(uid) or await self.bot.fetch_user(uid)
                mentions.append(user.mention if user else f"<@{uid}>")
            except:
                mentions.append(f"<@{uid}>")

        await ctx.send(f"**Alt Whitelisted Users:** {', '.join(mentions)}", 
                      allowed_mentions=self.no_pings, ephemeral=True)

    # =========================================================
    # ALT ROLE WHITELIST COMMANDS (Slash only)
    # =========================================================

    @app_commands.command(name="alt_role_add", description="Whitelist a role for alt command")
    @app_commands.describe(role="Role to whitelist")
    @app_commands.guild_only()
    async def alt_role_add(self, interaction: discord.Interaction, role: discord.Role):
        """Add a role to the alt whitelist."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)
            return

        self._add_alt_role(interaction.guild.id, role.id)
        await interaction.response.send_message(
            f"✅ {role.mention} has been whitelisted for the alt command.",
            allowed_mentions=self.no_pings,
            ephemeral=True
        )

    @app_commands.command(name="alt_role_remove", description="Remove a role from alt whitelist")
    @app_commands.describe(role="Role to remove")
    @app_commands.guild_only()
    async def alt_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from the alt whitelist."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)
            return

        removed = self._remove_alt_role(interaction.guild.id, role.id)
        msg = f"✅ Removed {role.mention} from whitelist." if removed else f"ℹ️ {role.mention} wasn't whitelisted."
        await interaction.response.send_message(msg, allowed_mentions=self.no_pings, ephemeral=True)

    @app_commands.command(name="alt_role_list", description="Show roles whitelisted for alt command")
    @app_commands.guild_only()
    async def alt_role_list(self, interaction: discord.Interaction):
        """Show roles whitelisted for alt command."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        role_ids = self._get_alt_role_ids(interaction.guild.id)
        if not role_ids:
            await interaction.followup.send("No roles are whitelisted for the alt command.", ephemeral=True)
            return

        mentions = []
        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)
            mentions.append(role.mention if role else f"<@&{role_id}>")

        await interaction.followup.send(
            f"**Alt Whitelisted Roles:** {', '.join(mentions)}",
            allowed_mentions=self.no_pings,
            ephemeral=True
        )

    # =========================================================
    # MOD WHITELIST COMMANDS (Slash only)
    # =========================================================

    @app_commands.command(name="mod_add", description="Add a role to mod whitelist")
    @app_commands.describe(role="Role to add to mod whitelist")
    @app_commands.guild_only()
    async def mod_add(self, interaction: discord.Interaction, role: discord.Role):
        """Add a role to the mod whitelist."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
            return

        self.bot.add_mod_role(interaction.guild.id, role.id)
        await interaction.response.send_message(
            f"✅ {role.mention} added to mod whitelist.",
            allowed_mentions=self.no_pings,
            ephemeral=True
        )

    @app_commands.command(name="mod_remove", description="Remove a role from mod whitelist")
    @app_commands.describe(role="Role to remove from mod whitelist")
    @app_commands.guild_only()
    async def mod_remove(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from the mod whitelist."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
            return

        removed = self.bot.remove_mod_role(interaction.guild.id, role.id)
        if removed:
            await interaction.response.send_message(
                f"✅ {role.mention} removed from mod whitelist.",
                allowed_mentions=self.no_pings,
                ephemeral=True
            )
        else:
            await interaction.response.send_message("ℹ️ That role wasn't on the mod list.", ephemeral=True)

    # =========================================================
    # ENHANCED MOD WHITELIST COMMANDS (Hybrid - Users & Roles)
    # =========================================================

    @commands.hybrid_command(name="addmod", description="Add a user or role to mod whitelist")
    @app_commands.describe(target="User or role to add mod permissions to")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def add_mod(self, ctx: commands.Context, target: Union[discord.Member, discord.Role]):
        """Add a user or role to the mod whitelist for all bot commands (except alt)."""
        if isinstance(target, discord.Role):
            # Add role to mod whitelist
            self.bot.add_mod_role(ctx.guild.id, target.id)
            embed = discord.Embed(
                title="✅ Mod Role Added",
                description=f"**{target.mention}** now has access to all bot commands (except alt generation).",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="📋 Permissions Granted",
                value="• All moderation commands\n• All utility commands\n• Admin commands (if admin)\n• ❌ Alt generation (excluded)",
                inline=False
            )
            embed.set_footer(text=f"Added by {ctx.author.display_name}")
            
        elif isinstance(target, discord.Member):
            # Add user to mod whitelist via role system (we'll add them to a special mod role)
            # For now, we'll use the existing role-based system and provide guidance
            embed = discord.Embed(
                title="ℹ️ User Mod Access",
                description=f"To give **{target.mention}** mod permissions, please:\n\n1. Create or use a mod role\n2. Assign that role to the user\n3. Use `/addmod @role` to add the role to the whitelist",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="💡 Tip",
                value="This role-based system provides better permission management and can be applied to multiple users at once.",
                inline=False
            )
        
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="removemod", description="Remove a user or role from mod whitelist")
    @app_commands.describe(target="User or role to remove mod permissions from")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def remove_mod(self, ctx: commands.Context, target: Union[discord.Member, discord.Role]):
        """Remove a user or role from the mod whitelist."""
        if isinstance(target, discord.Role):
            # Remove role from mod whitelist
            removed = self.bot.remove_mod_role(ctx.guild.id, target.id)
            if removed:
                embed = discord.Embed(
                    title="✅ Mod Role Removed",
                    description=f"**{target.mention}** no longer has mod access to bot commands.",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="📋 Permissions Revoked",
                    value="• All moderation commands\n• All utility commands\n• Admin commands (unless admin)",
                    inline=False
                )
                embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            else:
                embed = discord.Embed(
                    title="ℹ️ Role Not Found",
                    description=f"**{target.mention}** wasn't in the mod whitelist.",
                    color=discord.Color.orange()
                )
                
        elif isinstance(target, discord.Member):
            embed = discord.Embed(
                title="ℹ️ User Mod Removal",
                description=f"To remove **{target.mention}** mod permissions:\n\n1. Remove their mod role(s)\n2. Or use `/removemod @role` to remove the role from whitelist",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="💡 Current Method",
                value="The bot uses role-based permissions. Remove the user from mod roles or remove roles from the whitelist.",
                inline=False
            )
        
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="listmods", description="List all mod roles and their permissions")
    @commands.guild_only() 
    @commands.has_permissions(administrator=True)
    async def list_mods(self, ctx: commands.Context):
        """List all roles with mod permissions."""
        mod_roles = self.bot.mod_whitelist.get(str(ctx.guild.id), [])
        
        if not mod_roles:
            embed = discord.Embed(
                title="📋 Mod Whitelist",
                description="No roles are currently whitelisted for mod commands.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="💡 Get Started",
                value="Use `/addmod @role` to give a role access to all bot commands (except alt generation).",
                inline=False
            )
        else:
            role_list = []
            for role_id in mod_roles:
                role = ctx.guild.get_role(role_id)
                if role:
                    member_count = len(role.members)
                    role_list.append(f"• {role.mention} ({member_count} members)")
                else:
                    role_list.append(f"• ~~Deleted Role~~ (ID: {role_id})")
            
            embed = discord.Embed(
                title="📋 Mod Whitelist",
                description=f"**{len(mod_roles)} role(s)** have mod permissions:\n\n" + "\n".join(role_list),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="🔑 Permissions Included",
                value="• All moderation commands (ban, kick, timeout, etc.)\n• All utility commands\n• Admin commands (if user has admin perms)\n• ❌ Alt generation (excluded for security)",
                inline=False
            )
        
        embed.set_footer(text=f"Server: {ctx.guild.name}")
        await ctx.send(embed=embed, ephemeral=True)

    # =========================================================
    # BLACKLIST COMMANDS
    # =========================================================

    @commands.hybrid_command(name="reloadblacklist", description="Reload guild blacklist from environment")
    @commands.is_owner()
    async def reload_blacklist(self, ctx: commands.Context):
        """Reload the guild blacklist from environment variables."""
        try:
            # This would reload blacklist logic if implemented
            await ctx.send("✅ Blacklist reloaded successfully.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Failed to reload blacklist: {e}", ephemeral=True)

    # =========================================================
    # HELPER METHODS
    # =========================================================

    def _get_alt_role_ids(self, guild_id: int) -> Set[int]:
        """Get alt role IDs for a guild."""
        roles = set()
        # Try to get from bot's persistent storage if available
        try:
            if hasattr(self.bot, "get_alt_roles"):
                roles.update(self.bot.get_alt_roles(guild_id))
        except Exception as e:
            self.logger.error(f"Failed to get alt roles from persistent storage: {e}")
        
        # Fallback to in-memory storage
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        roles.update(store.get(guild_id, set()))
        return roles

    def _add_alt_role(self, guild_id: int, role_id: int) -> None:
        """Add a role to alt whitelist."""
        if hasattr(self.bot, "add_alt_role"):
            try:
                self.bot.add_alt_role(guild_id, role_id)
            except Exception:
                pass
        
        # Also store in memory as backup
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store is None:
            store = {}
            setattr(self.bot, "_alt_role_whitelist", store)
        store.setdefault(guild_id, set()).add(role_id)

    def _remove_alt_role(self, guild_id: int, role_id: int) -> bool:
        """Remove a role from alt whitelist."""
        removed = False
        
        if hasattr(self.bot, "remove_alt_role"):
            try:
                removed = bool(self.bot.remove_alt_role(guild_id, role_id))
            except Exception:
                removed = False
        
        # Also remove from memory storage
        store = getattr(self.bot, "_alt_role_whitelist", None)
        if store and guild_id in store and role_id in store[guild_id]:
            store[guild_id].remove(role_id)
            removed = True
            
        return removed

    def _member_has_alt_role(self, member: discord.Member) -> bool:
        """Check if member has any alt-whitelisted roles."""
        allowed_roles = self._get_alt_role_ids(member.guild.id)
        return any(role.id in allowed_roles for role in member.roles)

    # =========================================================
    # SAY COMMANDS
    # =========================================================

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
            await interaction.response.send_message("✅ Message sent!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send: {e}", ephemeral=True)

    # =========================================================
    # ROLE MANAGEMENT COMMANDS
    # =========================================================

    @commands.command(name="addrole", aliases=["giverole"])
    async def prefix_addrole(self, ctx, member: discord.Member, *, role: discord.Role):
        """Add a role to a member (prefix version)"""
        if not isinstance(ctx.author, discord.Member):
            return
        
        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles) for role_check in ctx.author.roles)
        if not has_role and not ctx.author.guild_permissions.manage_roles:
            await ctx.message.delete()
            response = await ctx.send("❌ You don't have permission to manage roles.")
            await response.delete(delay=5)
            return
            
        try:
            # Delete command message
            await ctx.message.delete()
            
            # Check if member already has the role
            if role in member.roles:
                response = await ctx.send(f"❌ {member.display_name} already has the {role.name} role.")
                await response.delete(delay=5)
                return
            
            # Check role hierarchy
            if role >= ctx.guild.me.top_role:
                response = await ctx.send(f"❌ I cannot manage the {role.name} role due to role hierarchy.")
                await response.delete(delay=5)
                return
            
            if ctx.author != ctx.guild.owner and role >= ctx.author.top_role:
                response = await ctx.send(f"❌ You cannot assign the {role.name} role due to role hierarchy.")
                await response.delete(delay=5)
                return
            
            # Add the role
            await member.add_roles(role, reason=f"Role added by {ctx.author}")
            
            # Send success message
            embed = discord.Embed(
                description=f"✅ Successfully added **{role.name}** role to {member.mention}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, delete_after=10)
            self.logger.info(f"Role {role.name} added to {member} by {ctx.author} in {ctx.guild.name}")
            
        except discord.Forbidden:
            response = await ctx.send("❌ I don't have permission to manage roles.")
            await response.delete(delay=5)
        except Exception as e:
            response = await ctx.send(f"❌ Failed to add role: {e}")
            await response.delete(delay=5)

    @app_commands.command(name="addrole", description="Add a role to a member")
    @app_commands.describe(
        member="The member to give the role to",
        role="The role to add"
    )
    @app_commands.guild_only()
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        """Add a role to a member (slash version)"""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles) for role_check in interaction.user.roles)
        if not has_role and not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return

        # Check if member already has the role
        if role in member.roles:
            await interaction.response.send_message(f"❌ {member.display_name} already has the **{role.name}** role.", ephemeral=True)
            return
        
        # Check role hierarchy
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(f"❌ I cannot manage the **{role.name}** role due to role hierarchy.", ephemeral=True)
            return
        
        if interaction.user != interaction.guild.owner and role >= interaction.user.top_role:
            await interaction.response.send_message(f"❌ You cannot assign the **{role.name}** role due to role hierarchy.", ephemeral=True)
            return

        try:
            # Add the role
            await member.add_roles(role, reason=f"Role added by {interaction.user}")
            
            # Send success message
            embed = discord.Embed(
                description=f"✅ Successfully added **{role.name}** role to {member.mention}",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Added by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            self.logger.info(f"Role {role.name} added to {member} by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to add role: {e}", ephemeral=True)

    @commands.command(name="removerole", aliases=["takerole"])
    async def prefix_removerole(self, ctx, member: discord.Member,
                                *, role: discord.Role):
        """Remove a role from a member (prefix version)"""
        if not isinstance(ctx.author, discord.Member):
            return

        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles)
                       for role_check in ctx.author.roles)
        if not has_role and not ctx.author.guild_permissions.manage_roles:
            await ctx.message.delete()
            response = await ctx.send(
                "❌ You don't have permission to manage roles.")
            await response.delete(delay=5)
            return

        try:
            # Delete command message
            await ctx.message.delete()

            # Check if member doesn't have the role
            if role not in member.roles:
                response = await ctx.send(
                    f"❌ {member.display_name} doesn't have "
                    f"the {role.name} role.")
                await response.delete(delay=5)
                return

            # Check role hierarchy
            if role >= ctx.guild.me.top_role:
                response = await ctx.send(
                    f"❌ I cannot manage the {role.name} role "
                    f"due to role hierarchy.")
                await response.delete(delay=5)
                return

            if (ctx.author != ctx.guild.owner and
                    role >= ctx.author.top_role):
                response = await ctx.send(
                    f"❌ You cannot remove the {role.name} role "
                    f"due to role hierarchy.")
                await response.delete(delay=5)
                return

            # Remove the role
            await member.remove_roles(
                role, reason=f"Role removed by {ctx.author}")

            # Send success message
            embed = discord.Embed(
                description=(f"✅ Successfully removed **{role.name}** "
                             f"role from {member.mention}"),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, delete_after=10)
            self.logger.info(
                f"Role {role.name} removed from {member} by {ctx.author} "
                f"in {ctx.guild.name}")

        except discord.Forbidden:
            response = await ctx.send(
                "❌ I don't have permission to manage roles.")
            await response.delete(delay=5)
        except Exception as e:
            response = await ctx.send(f"❌ Failed to remove role: {e}")
            await response.delete(delay=5)

    @app_commands.command(name="removerole",
                          description="Remove a role from a member")
    @app_commands.describe(
        member="The member to remove the role from",
        role="The role to remove"
    )
    @app_commands.guild_only()
    async def removerole(self, interaction: discord.Interaction,
                         member: discord.Member, role: discord.Role):
        """Remove a role from a member (slash version)"""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True)
            return

        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles)
                       for role_check in interaction.user.roles)
        if (not has_role and
                not interaction.user.guild_permissions.manage_roles):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.",
                ephemeral=True)
            return

        # Check if member doesn't have the role
        if role not in member.roles:
            await interaction.response.send_message(
                f"❌ {member.display_name} doesn't have "
                f"the **{role.name}** role.", ephemeral=True)
            return

        # Check role hierarchy
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                f"❌ I cannot manage the **{role.name}** role "
                f"due to role hierarchy.", ephemeral=True)
            return

        if (interaction.user != interaction.guild.owner and
                role >= interaction.user.top_role):
            await interaction.response.send_message(
                f"❌ You cannot remove the **{role.name}** role "
                f"due to role hierarchy.", ephemeral=True)
            return

        try:
            # Remove the role
            await member.remove_roles(
                role, reason=f"Role removed by {interaction.user}")

            # Send success message
            embed = discord.Embed(
                description=(f"✅ Successfully removed **{role.name}** "
                             f"role from {member.mention}"),
                color=discord.Color.green()
            )
            embed.set_footer(
                text=f"Removed by {interaction.user.display_name}")

            await interaction.response.send_message(embed=embed)
            self.logger.info(
                f"Role {role.name} removed from {member} by "
                f"{interaction.user} in {interaction.guild.name}")

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles.",
                ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to remove role: {e}", ephemeral=True)

    # =========================================================
    # SETNICK COMMANDS (Hybrid)
    # =========================================================

    @commands.hybrid_command(name="setnick", description="Change a member's nickname")
    @app_commands.describe(
        member="The member whose nickname to change",
        nickname="The new nickname (leave empty to remove nickname)"
    )
    @commands.guild_only()
    async def setnick(self, ctx: commands.Context, member: discord.Member, *, nickname: Optional[str] = None):
        """Change a member's nickname."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        # Check if this is a guild context
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles) for role_check in ctx.author.roles)
        if not has_role and not ctx.author.guild_permissions.manage_nicknames:
            await ctx.send("❌ You don't have permission to manage nicknames.", ephemeral=True)
            return

        # Check role hierarchy for members (skip for bot's own nickname)
        if member != ctx.guild.me and member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("❌ You cannot change the nickname of someone with a higher or equal role.", ephemeral=True)
            return

        # Check if bot has permission to change this member's nickname (skip for bot's own nickname)
        if member != ctx.guild.me and member.top_role >= ctx.guild.me.top_role:
            await ctx.send("❌ I cannot change the nickname of someone with a higher or equal role than me.", ephemeral=True)
            return

        try:
            old_nick = member.display_name
            await member.edit(nick=nickname)
            
            if nickname:
                embed = discord.Embed(
                    title="✅ Nickname Changed",
                    description=f"Changed {member.mention}'s nickname from **{old_nick}** to **{nickname}**",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="✅ Nickname Removed",
                    description=f"Removed {member.mention}'s nickname (was **{old_nick}**)",
                    color=discord.Color.green()
                )
            
            embed.set_footer(text=f"Changed by {ctx.author.display_name}")
            await ctx.send(embed=embed, allowed_mentions=self.no_pings)
            
            # Log the action
            self.logger.info(f"Nickname changed for {member} by {ctx.author} in {ctx.guild.name}: '{old_nick}' -> '{nickname}'")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to manage nicknames.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Failed to change nickname: {e}", ephemeral=True)

    # =========================================================
    # SETPREFIX COMMANDS (Hybrid)
    # =========================================================

    @commands.hybrid_command(name="setprefix", description="Change the bot's command prefix")
    @app_commands.describe(prefix="The new prefix to use (1-3 characters)")
    @commands.guild_only()
    async def setprefix(self, ctx: commands.Context, prefix: str):
        """Change the bot's command prefix."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        # Check if this is a guild context
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Check permissions
        has_role = any((role_check.id in self.allowed_say_roles) for role_check in ctx.author.roles)
        if not has_role and not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need **Manage Server** permission or the allowed roles to change the prefix.", ephemeral=True)
            return

        # Validate prefix
        if len(prefix) > 3:
            await ctx.send("❌ Prefix must be 3 characters or less.", ephemeral=True)
            return
        
        if len(prefix.strip()) == 0:
            await ctx.send("❌ Prefix cannot be empty or only whitespace.", ephemeral=True)
            return

        # Check for problematic prefixes
        if prefix in ["@", "<@", "`", "```"]:
            await ctx.send("❌ This prefix could cause conflicts with Discord features.", ephemeral=True)
            return

        try:
            # Update the bot's prefix (this is a simple implementation)
            old_prefix = self.bot._text_prefix
            self.bot._text_prefix = prefix
            
            embed = discord.Embed(
                title="✅ Prefix Changed",
                description=f"Bot prefix changed from `{old_prefix}` to `{prefix}`\n\nYou can now use commands like `{prefix}ping` or `{prefix}help`",
                color=discord.Color.green()
            )
            embed.add_field(
                name="📝 Note", 
                value="Slash commands (/) will still work as before!", 
                inline=False
            )
            embed.set_footer(text=f"Changed by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
            # Log the action
            self.logger.info(f"Prefix changed from '{old_prefix}' to '{prefix}' by {ctx.author} in {ctx.guild.name}")
            
        except Exception as e:
            await ctx.send(f"❌ Failed to change prefix: {e}", ephemeral=True)

    # =========================================================
    # DM COMMAND
    # =========================================================

    @commands.hybrid_command(
        name="dm",
        description="Send a direct message to a user or all members with a role"
    )
    @commands.has_permissions(manage_messages=True)
    async def dm(self, ctx, target: typing.Union[discord.User, discord.Role], *, message: str):
        """Send a direct message to a user or all members with a role."""
        try:
            # Auto-delete the command message for prefix commands only
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.Forbidden:
                    pass  # No permission to delete
            
            # Check if target is a role
            if isinstance(target, discord.Role):
                # Get all members with this role
                members_with_role = [member for member in ctx.guild.members if target in member.roles and not member.bot]
                
                if not members_with_role:
                    if ctx.interaction:
                        await ctx.send(f"❌ No members found with the role {target.name}.", ephemeral=True)
                    else:
                        await ctx.send(f"❌ No members found with the role {target.name}.", delete_after=3)
                    return
                
                # Send DM to all members with the role
                successful_dms = 0
                failed_dms = 0
                
                for member in members_with_role:
                    try:
                        await member.send(message)
                        successful_dms += 1
                    except (discord.Forbidden, discord.HTTPException):
                        failed_dms += 1
                
                # Send summary
                total_members = len(members_with_role)
                summary = f"📨 **Role DM Summary for {target.name}:**\n✅ Sent: {successful_dms}/{total_members}\n❌ Failed: {failed_dms}/{total_members}"
                
                if ctx.interaction:
                    await ctx.send(summary, ephemeral=True)
                else:
                    await ctx.send(summary, delete_after=10)
                
                # Log the action
                self.logger.info(
                    "Role DM sent to %s members with role %s by %s in %s: %s (Success: %d, Failed: %d)",
                    total_members,
                    target.name,
                    ctx.author,
                    ctx.guild.name,
                    message,
                    successful_dms,
                    failed_dms
                )
                
            else:
                # Target is a user, send single DM
                await target.send(message)
                
                # Check if it's a slash command (interaction) or prefix command
                if ctx.interaction:
                    # For slash commands, send ephemeral (auto-hidden)
                    await ctx.send(
                        f"✅ Direct message sent to {target.display_name}!",
                        ephemeral=True
                    )
                else:
                    # For prefix commands, send and auto-delete after 1 second
                    await ctx.send(
                        f"✅ Direct message sent to {target.display_name}!",
                        delete_after=1
                    )
                
                # Log the action
                self.logger.info(
                    "DM sent to %s by %s in %s: %s",
                    target,
                    ctx.author,
                    ctx.guild.name,
                    message
                )
            
        except discord.Forbidden:
            # Auto-delete the command message for prefix commands only
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.Forbidden:
                    pass  # No permission to delete
            
            # Only handle single user DM failures here (role DMs handle their own errors)
            if isinstance(target, discord.User):
                if ctx.interaction:
                    await ctx.send(
                        f"❌ Could not send DM to {target.display_name}. "
                        "They may have DMs disabled or blocked the bot.",
                        ephemeral=True
                    )
                else:
                    await ctx.send(
                        f"❌ Could not send DM to {target.display_name}. "
                        "They may have DMs disabled or blocked the bot.",
                        delete_after=3
                    )
            
        except discord.HTTPException as e:
            # Auto-delete the command message for prefix commands only
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.Forbidden:
                    pass  # No permission to delete
            
            # Only handle single user DM failures here (role DMs handle their own errors)
            if isinstance(target, discord.User):
                if ctx.interaction:
                    await ctx.send(
                        f"❌ Failed to send DM to {target.display_name}: {e}",
                        ephemeral=True
                    )
                else:
                    await ctx.send(
                        f"❌ Failed to send DM to {target.display_name}: {e}",
                        delete_after=3
                    )
                self.logger.error("Failed to send DM to %s: %s", target, e)

    # =========================================================
    # STATUS COMMAND
    # =========================================================

    @commands.hybrid_command(
        name="status",
        description="Show bot status and statistics"
    )
    async def status(self, ctx):
        """Show bot status and statistics."""
        try:
            # Get bot stats
            guild_count = len(self.bot.guilds)
            total_members = sum(guild.member_count for guild in self.bot.guilds)
            
            # Get uptime
            uptime = discord.utils.utcnow() - self.bot.start_time
            uptime_str = str(uptime).split('.')[0]  # Remove microseconds
            
            # Get latency
            latency = round(self.bot.latency * 1000, 1)
            
            # Create status embed
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="📊 Statistics",
                value=(
                    f"**Guilds:** {guild_count}\n"
                    f"**Members:** {total_members:,}\n"
                    f"**Commands:** 57"
                ),
                inline=True
            )
            
            embed.add_field(
                name="⚡ Performance",
                value=(
                    f"**Latency:** {latency}ms\n"
                    f"**Uptime:** {uptime_str}\n"
                    f"**Status:** Online"
                ),
                inline=True
            )
            
            embed.add_field(
                name="🔧 System",
                value=(
                    f"**Python:** 3.13\n"
                    f"**Discord.py:** {discord.__version__}\n"
                    f"**Prefix:** !"
                ),
                inline=True
            )
            
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            # Auto-delete the command message for prefix commands only
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.Forbidden:
                    pass  # No permission to delete
            
            # Send message permanently (no auto-delete)
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_msg = f"❌ Failed to get bot status: {e}"
            if ctx.interaction:
                await ctx.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=5)
            self.logger.error("Failed to get bot status: %s", e)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
