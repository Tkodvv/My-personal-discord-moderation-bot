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

class UtilityCog(commands.Cog):
    """Utility commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = utcnow()

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx: commands.Context):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms", ephemeral=True)

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx: commands.Context):
        """Check the bot's uptime."""
        uptime_duration = utcnow() - self.start_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        await ctx.send(f"⏰ Bot uptime: `{uptime_str}`", ephemeral=True)

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
                            # Send first message with text
                            first_url = data[0].get("url") if data else None
                            if first_url:
                                await ctx.send(f"🐱 Here {'is your cat' if n == 1 else f'are your {n} cats'}:\n{first_url}")
                                
                                # Send additional cats if requested
                                for item in data[1:]:
                                    cat_url = item.get("url")
                                    if cat_url:
                                        await asyncio.sleep(0.5)  # Small delay between sends
                                        await ctx.send(cat_url)
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
                            await ctx.send(f"🐶 Here's your dog:\n{dog_url}")
                            return
                    
                    await ctx.send(f"❌ Dog API error: HTTP {response.status}", ephemeral=True)
                    
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch dog: {str(e)}", ephemeral=True)

    @commands.hybrid_command(name="invite", description="Get bot invite link")
    async def invite(self, ctx: commands.Context):
        """Get the bot's invite link."""
        if not self.bot.user:
            await ctx.send("❌ Bot user not available.", ephemeral=True)
            return
            
        permissions = discord.Permissions(
            ban_members=True,
            kick_members=True,
            manage_messages=True,
            manage_roles=True,
            view_audit_log=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            use_slash_commands=True
        )
        
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=permissions)
        
        embed = discord.Embed(
            title="🤖 Bot Invite Link",
            description=f"[Click here to invite me to your server!]({invite_url})",
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
