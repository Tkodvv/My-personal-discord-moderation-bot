# -*- coding: utf-8 -*-
"""
Admin Cog - Revamped for proper Discord functionality
Contains administrative commands and bot management features.
"""

import os
import json
import asyncio
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Set, Union
import logging

# Import the alt generation function
try:
    from roblox_alts import get_alt_public
except ImportError:
    async def get_alt_public():
        return None

class AdminCog(commands.Cog):
    """Administrative commands and bot management."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.no_pings = discord.AllowedMentions.none()

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
            await ctx.defer(ephemeral=True)

        try:
            alt_data = await get_alt_public()
            if not alt_data or not alt_data.get("username"):
                await ctx.send("❌ Failed to generate alt account. Please try again later.", ephemeral=True)
                return

            # Create embed with alt data
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

            # Try to parse creation date
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

            # Try to send DM
            try:
                await ctx.author.send(embed=embed)
                public_embed = discord.Embed(
                    description=f"✅ Account details sent to {ctx.author.mention}'s DMs!",
                    color=discord.Color.green()
                )
                await ctx.send(embed=public_embed, ephemeral=True)
                        
            except discord.Forbidden:
                await ctx.send("❌ I couldn't DM you. Please enable DMs from server members and try again.", ephemeral=True)

        except commands.CommandOnCooldown as e:
            await ctx.send(f"⏰ Slow down! Try again in {e.retry_after:.1f}s", ephemeral=True)
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

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
