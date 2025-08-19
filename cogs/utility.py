# -*- coding: utf-8 -*-
"""
Utility Cog - Revamped for proper Discord functionality
Contains utility commands like userinfo, avatar, server info, status lists, etc.
"""

import os
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from discord.utils import utcnow, format_dt
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class EmbedModal(discord.ui.Modal, title='Create Custom Embed'):
    """Modal for creating custom embeds with proper formatting."""
    
    def __init__(self):
        super().__init__()
        
    title_input = discord.ui.TextInput(
        label='Title',
        placeholder='Enter the embed title (optional)',
        required=False,
        max_length=256
    )
    
    description_input = discord.ui.TextInput(
        label='Description',
        placeholder='Enter the embed description/content',
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000
    )
    
    color_input = discord.ui.TextInput(
        label='Color',
        placeholder='Enter color (hex like #ff0000 or name like red)',
        required=False,
        max_length=50
    )
    
    author_input = discord.ui.TextInput(
        label='Author Name',
        placeholder='Enter author name (optional)',
        required=False,
        max_length=256
    )
    
    author_icon_input = discord.ui.TextInput(
        label='Author Icon URL',
        placeholder='Enter author icon URL (optional)',
        required=False,
        max_length=2048
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need `manage_messages` permission to use this command.", ephemeral=True)
            return
            
        # Validate input
        if not self.title_input.value and not self.description_input.value:
            await interaction.response.send_message("❌ You must provide at least a title or description for the embed.", ephemeral=True)
            return
            
        # Create embed
        embed = discord.Embed()
        
        # Set title and description
        if self.title_input.value:
            embed.title = self.title_input.value
        if self.description_input.value:
            embed.description = self.description_input.value
            
        # Set color
        if self.color_input.value:
            try:
                color_value = self.color_input.value.strip()
                # Handle hex colors
                if color_value.startswith('#'):
                    embed.color = discord.Color(int(color_value[1:], 16))
                # Handle named colors
                elif hasattr(discord.Color, color_value.lower()):
                    embed.color = getattr(discord.Color, color_value.lower())()
                else:
                    # Try to parse as hex without #
                    embed.color = discord.Color(int(color_value, 16))
            except (ValueError, AttributeError):
                embed.color = discord.Color.blue()  # Default color
        else:
            embed.color = discord.Color.blue()
            
        # Set author
        if self.author_input.value:
            try:
                if self.author_icon_input.value:
                    embed.set_author(name=self.author_input.value, icon_url=self.author_icon_input.value)
                else:
                    embed.set_author(name=self.author_input.value)
            except:
                embed.set_author(name=self.author_input.value)  # Fallback without icon
                
        # Send ephemeral response first (hides the slash command usage)
        await interaction.response.send_message("✅", ephemeral=True)
        # Then send the actual embed publicly
        await interaction.followup.send(embed=embed)


class UtilityCog(commands.Cog):
    """Utility commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = utcnow()

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx: commands.Context):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms")

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx: commands.Context):
        """Check the bot's uptime."""
        uptime_duration = utcnow() - self.start_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        await ctx.send(f"⏰ Bot uptime: `{uptime_str}`", ephemeral=True)

    @app_commands.command(name="embed", description="Create a custom embed message with popup form")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_slash(self, interaction: discord.Interaction):
        """Create a custom embed message using a modal popup."""
        modal = EmbedModal()
        await interaction.response.send_modal(modal)

    @commands.hybrid_command(name="userinfo", description="Get information about a user")
    @app_commands.describe(user="User to get info about")
    async def userinfo(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Get information about a user."""
        target = user or ctx.author
        
        embed = discord.Embed(
            title=f"User Info - {target.display_name}",
            color=target.color,
            timestamp=utcnow()
        )
        
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="User Info",
            value=f"**Username:** {target}\n"
                  f"**Display Name:** {target.display_name}\n"
                  f"**ID:** {target.id}\n"
                  f"**Bot:** {'Yes' if target.bot else 'No'}",
            inline=True
        )
        
        embed.add_field(
            name="Dates",
            value=f"**Created:** {format_dt(target.created_at, 'R')}\n"
                  f"**Joined:** {format_dt(target.joined_at, 'R') if target.joined_at else 'Unknown'}",
            inline=True
        )
        
        if target.roles[1:]:  # Exclude @everyone role
            roles = [role.mention for role in target.roles[1:]]
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=" ".join(roles) if len(" ".join(roles)) <= 1024 else f"{len(roles)} roles",
                inline=False
            )
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Get information about this server")
    async def serverinfo(self, ctx: commands.Context):
        """Get information about the server."""
        guild = ctx.guild
        if not guild:
            await ctx.send("❌ This command can only be used in a server.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title=f"Server Info - {guild.name}",
            color=discord.Color.blue(),
            timestamp=utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        embed.add_field(
            name="General Info",
            value=f"**Name:** {guild.name}\n"
                  f"**ID:** {guild.id}\n"
                  f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
                  f"**Created:** {format_dt(guild.created_at, 'R')}",
            inline=True
        )
        
        embed.add_field(
            name="Stats",
            value=f"**Members:** {guild.member_count}\n"
                  f"**Channels:** {len(guild.channels)}\n"
                  f"**Roles:** {len(guild.roles)}\n"
                  f"**Emojis:** {len(guild.emojis)}",
            inline=True
        )
        
        embed.add_field(
            name="Features",
            value=f"**Verification Level:** {guild.verification_level.name.title()}\n"
                  f"**Boost Level:** {guild.premium_tier}\n"
                  f"**Boost Count:** {guild.premium_subscription_count or 0}",
            inline=True
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(user="User to get avatar of")
    async def avatar(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Get a user's avatar."""
        target = user or ctx.author
        
        embed = discord.Embed(
            title=f"{target.display_name}'s Avatar",
            color=target.color,
            timestamp=utcnow()
        )
        
        embed.set_image(url=target.display_avatar.url)
        embed.add_field(
            name="Links",
            value=f"[PNG]({target.display_avatar.replace(format='png').url}) | "
                  f"[JPG]({target.display_avatar.replace(format='jpg').url}) | "
                  f"[WEBP]({target.display_avatar.replace(format='webp').url})",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="cat", description="Get random cat images (1-5)")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @app_commands.describe(count="How many cats to fetch (1-5)")
    async def cat(self, ctx: commands.Context, count: Optional[int] = 1):
        """Get random cat images (1-5)."""
        # Validate count parameter
        n = max(1, min(int(count or 1), 5))
        
        # Defer for slash commands that might take time
        if ctx.interaction:
            await ctx.defer()

        api_key = os.getenv("CAT_API_KEY")
        url = "https://api.thecatapi.com/v1/images/search"
        headers = {"x-api-key": api_key} if api_key else {}
        params = {"limit": n}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and isinstance(data, list):
                            # Create embed for each cat
                            for item in data:
                                cat_url = item.get("url")
                                if cat_url:
                                    embed = discord.Embed(
                                        title="🐱 Random Cat",
                                        color=discord.Color.orange()
                                    )
                                    embed.set_image(url=cat_url)
                                    await ctx.send(embed=embed)
                                    if len(data) > 1:
                                        await asyncio.sleep(0.5)  # Small delay between multiple cats
                            return
                    else:
                        await ctx.send(f"❌ Cat API error: HTTP {response.status}", ephemeral=True)
                        return

        except asyncio.TimeoutError:
            await ctx.send("❌ Cat API request timed out. Please try again later!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch cats: {str(e)}", ephemeral=True)

    @commands.hybrid_command(name="dog", description="Get a random dog image")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def dog(self, ctx: commands.Context):
        """Get a random dog image."""
        if ctx.interaction:
            await ctx.defer()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://random.dog/woof.json", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        dog_url = data.get("url")
                        if dog_url:
                            await ctx.send(dog_url)  # Send only the image URL for cleaner look
                            return
                    
                    await ctx.send(f"❌ Dog API error: HTTP {response.status}", ephemeral=True)
                    
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch dog: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
