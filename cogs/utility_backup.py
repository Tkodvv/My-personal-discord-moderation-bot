# -*- coding: utf-8 -*-
"""
Utility Cog
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
        try:
            latency = round(self.bot.latency * 1000)
            await ctx.send(f"🏓 Pong! Latency: {latency}ms", ephemeral=True)
        except Exception as e:
            print(f"Ping error: {e}")
            await ctx.send("❌ Ping failed", ephemeral=True)

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
                  f"**ID:** {target.id}\n"
                  f"**Created:** {format_dt(target.created_at, 'R')}\n"
                  f"**Joined:** {format_dt(target.joined_at, 'R') if hasattr(target, 'joined_at') else 'N/A'}\n"
                  f"**Bot:** {'Yes' if target.bot else 'No'}",
            inline=False
        )
        
        if isinstance(target, discord.Member) and target.roles[1:]:
            roles = [role.mention for role in reversed(target.roles[1:])]  # All roles except @everyone
            embed.add_field(
                name=f"Roles [{len(roles)}]",
                value=" ".join(roles) if len(" ".join(roles)) <= 1024 else f"{len(roles)} roles",
                inline=False
            )

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, ctx):
        """Get information about the server."""
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f"Server Info - {guild.name}",
            color=discord.Color.blue(),
            timestamp=utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(
            name="General",
            value=f"**Owner:** {guild.owner.mention}\n"
                  f"**Created:** {format_dt(guild.created_at, 'R')}\n"
                  f"**Members:** {guild.member_count:,}",
            inline=False
        )
        
        channel_info = f"**Text:** {len(guild.text_channels)}\n" \
                      f"**Voice:** {len(guild.voice_channels)}\n" \
                      f"**Categories:** {len(guild.categories)}"
        embed.add_field(name="Channels", value=channel_info, inline=True)
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(user="User to get avatar for")
    async def avatar(self, ctx, user: Optional[discord.Member] = None):
        """Get a user's avatar."""
        target = user or ctx.author if isinstance(ctx, commands.Context) else ctx.user
        
        embed = discord.Embed(
            title=f"Avatar - {target.display_name}",
            color=target.color,
            timestamp=utcnow()
        )
        embed.set_image(url=target.display_avatar.url)
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="cat", description="Get random cat images (1-5)")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @app_commands.describe(count="How many cats to fetch (1-5)")
    async def cat(self, ctx: commands.Context, count: Optional[int] = 1):
        """Get random cat images (1-5)."""
        try:
            # Validate count parameter
            n = max(1, min(int(count or 1), 5))
            
            # Simple test response first
            await ctx.send(f"🐱 Testing cat command with count: {n}", ephemeral=True)
            
        except Exception as e:
            print(f"Cat command error: {e}")
            await ctx.send(f"❌ Cat command error: {str(e)}", ephemeral=True)

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx):
        """Check how long the bot has been running."""
        delta = utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        parts = []
        if days > 0:
            parts.append(f"{days} days")
        if hours > 0:
            parts.append(f"{hours} hours")
        if minutes > 0:
            parts.append(f"{minutes} minutes")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} seconds")

        uptime_str = ", ".join(parts)
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(f"🕒 Bot has been online for: {uptime_str}")
        else:
            await ctx.send(f"🕒 Bot has been online for: {uptime_str}")


async def setup(bot):
    """Set up the utility cog."""
    await bot.add_cog(UtilityCog(bot))

    async def _send_command_response(self, ctx, content=None, *, embed=None, ephemeral=False, delete_after=None):
        """Helper to send messages consistently across command types"""
        try:
            # For interactions (slash commands)
            if isinstance(ctx, discord.Interaction):
                try:
                    if not ctx.response.is_done():
                        if embed:
                            await ctx.response.send_message(embed=embed, ephemeral=ephemeral)
                        else:
                            await ctx.response.send_message(content, ephemeral=ephemeral)
                        return await ctx.original_response()
                    else:
                        if embed:
                            return await ctx.followup.send(embed=embed, ephemeral=ephemeral)
                        else:
                            return await ctx.followup.send(content, ephemeral=ephemeral)
                except discord.errors.InteractionResponded:
                    if embed:
                        return await ctx.followup.send(embed=embed, ephemeral=ephemeral)
                    else:
                        return await ctx.followup.send(content, ephemeral=ephemeral)
            # For prefix commands
            else:
                try:
                    if embed:
                        return await ctx.send(embed=embed, delete_after=delete_after)
                    else:
                        return await ctx.send(content, delete_after=delete_after)
                except discord.HTTPException as e:
                    self.logger.error(f"HTTP error sending message: {e}")
                except Exception as e:
                    self.logger.error(f"Error sending message: {e}")
        except Exception as e:
            self.logger.error(f"Error in _send_command_response: {e}")
        return None

    async def delete_command_message(self, ctx):
        """Helper to delete the command message for prefix commands."""
        # Return immediately for slash commands
        if isinstance(ctx, discord.Interaction) or not hasattr(ctx, 'message'):
            return

        # For prefix commands only
        try:
            if ctx.message:
                try:
                    await ctx.message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass  # Ignore any deletion-related errors
        except Exception:
            pass  # Ignore any other errors

    @commands.hybrid_command(name="cat", description="Send random cat image(s) (1–5)")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @app_commands.describe(count="How many cats to fetch (1-5)")
    async def cat(self, ctx, count: Optional[int] = 1):
        """Send random cat image(s) (1–5)."""
        try:
            n = max(1, min(int(count or 1), 5))
        except (ValueError, TypeError):
            n = 1

        # Handle command types
        if isinstance(ctx, discord.Interaction):
            try:
                await ctx.response.defer(thinking=True)
            except discord.errors.InteractionResponded:
                pass
        elif isinstance(ctx, commands.Context):  # Only for prefix commands
            if hasattr(ctx, 'message') and ctx.message and not isinstance(ctx.message, discord.InteractionMessage):
                try:
                    await ctx.message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                    pass

        # Fetch cat images
        api_key = os.getenv("CAT_API_KEY")
        url = "https://api.thecatapi.com/v1/images/search"
        params = {"limit": n, "size": "full"}
        headers = {"x-api-key": api_key} if api_key else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=15) as r:
                    if r.status != 200:
                        await self._send_command_response(ctx, "❌ Cat API error. Try again later.", ephemeral=True, delete_after=5)
                        return
                    data = await r.json()
        except Exception as e:
            self.logger.error(f"Cat API error: {e}")
            await self._send_command_response(ctx, "❌ Couldn't reach the cat server. Try again later.", ephemeral=True, delete_after=5)
            return

        if not isinstance(data, list) or not data:
            await self._send_command_response(ctx, "❌ No cats found.", ephemeral=True, delete_after=5)
            return

        sent_count = 0
        for item in data[:n]:
            img = item.get("url")
            if img:
                try:
                    await self._send_command_response(ctx, img)
                    sent_count += 1
                    await asyncio.sleep(0.5)  # Small delay between images
                except Exception as e:
                    self.logger.error(f"Error sending cat image: {e}")
                    continue

        if sent_count == 0:
            await self._send_command_response(ctx, "❌ Cat API returned no usable images.", ephemeral=True, delete_after=5)

    @commands.hybrid_command(name="userinfo", description="Get information about a user")
    @app_commands.describe(user="User to get info about")
    async def userinfo(self, ctx, user: Optional[discord.Member] = None):
        """Get information about a user."""
        target = user or ctx.author
        roles = [role.mention for role in target.roles[1:]]  # All roles except @everyone
        roles.reverse()  # Display highest roles first

        embed = discord.Embed(
            title=f"User Info - {target.display_name}",
            color=target.color,
            timestamp=utcnow()
        )

        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(
            name="User Info",
            value=f"**Username:** {target.name}\n"
                  f"**Display Name:** {target.display_name}\n"
                  f"**ID:** {target.id}\n"
                  f"**Account Created:** {format_dt(target.created_at, 'R')}\n"
                  f"**Server Join Date:** {format_dt(target.joined_at, 'R')}\n"
                  f"**Bot Account:** {'Yes' if target.bot else 'No'}",
            inline=False
        )

        if roles:
            embed.add_field(
                name=f"Roles [{len(roles)}]",
                value=" ".join(roles) if len(" ".join(roles)) <= 1024 else f"{len(roles)} roles",
                inline=False
            )

        await self._send_command_response(ctx, embed=embed)
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, ctx):
        """Get information about the server."""
        guild = ctx.guild
        
        # Get member counts
        total_members = guild.member_count
        human_members = len([m for m in guild.members if not m.bot])
        bot_members = total_members - human_members
        
        # Get channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        # Create embed
        embed = discord.Embed(
            title=f"Server Info - {guild.name}",
            color=discord.Color.blue(),
            timestamp=utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        # Basic server info
        embed.add_field(
            name="Basic Info",
            value=f"**Owner:** {guild.owner.mention}\n"
                  f"**Created:** {format_dt(guild.created_at, 'R')}\n"
                  f"**Server ID:** {guild.id}",
            inline=False
        )
        
        # Member counts
        embed.add_field(
            name="Members",
            value=f"**Total:** {total_members:,}\n"
                  f"**Humans:** {human_members:,}\n"
                  f"**Bots:** {bot_members:,}",
            inline=True
        )
        
        # Channel counts
        embed.add_field(
            name="Channels",
            value=f"**Text:** {text_channels}\n"
                  f"**Voice:** {voice_channels}\n"
                  f"**Categories:** {categories}",
            inline=True
        )
        
        # Server features
        if guild.features:
            embed.add_field(
                name="Features",
                value="\n".join(f"• {feature.replace('_', ' ').title()}" for feature in guild.features),
                inline=False
            )

        await self._send_command_response(ctx, embed=embed)
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(user="User to get avatar for")
    async def avatar(self, ctx, user: Optional[discord.Member] = None):
        """Get a user's avatar."""
        target = user or ctx.author
        
        embed = discord.Embed(
            title=f"Avatar - {target.display_name}",
            color=target.color,
            timestamp=utcnow()
        )
        
        embed.set_image(url=target.display_avatar.url)
        
        await self._send_command_response(ctx, embed=embed)
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx):
        """Check the bot's latency."""
        start_time = utcnow()
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            end_time = utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000
            await ctx.followup.send(f"🏓 Pong!\nBot Latency: {response_time:.2f}ms\nWebSocket Latency: {self.bot.latency * 1000:.2f}ms")
        else:
            msg = await ctx.send("🏓 Pong!")
            end_time = utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000
            await msg.edit(content=f"🏓 Pong!\nBot Latency: {response_time:.2f}ms\nWebSocket Latency: {self.bot.latency * 1000:.2f}ms")
            await self.delete_command_message(ctx)

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx):
        """Check how long the bot has been running."""
        current_time = utcnow()
        uptime = current_time - self.start_time
        
        # Format uptime
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
        uptime_str = ", ".join(parts)
        
        await self._send_command_response(ctx, f"🕒 Bot has been online for: {uptime_str}")
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="poll", description="Create a poll")
    @app_commands.describe(
        question="The poll question",
        options="Options separated by | (e.g., 'yes|no|maybe')"
    )
    async def poll(self, ctx, question: str, options: Optional[str] = None):
        """Create a poll with reactions."""
        if not options:
            # Yes/No poll
            embed = discord.Embed(
                title="📊 Poll",
                description=f"{question}",
                color=discord.Color.blue(),
                timestamp=utcnow()
            )
            embed.set_footer(text=f"Asked by {ctx.author.display_name}")
            
            msg = await self._send_command_response(ctx, embed=embed)
            if isinstance(msg, discord.Message):
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")
                self._poll_reaction_whitelist[msg.id] = {"👍", "👎"}
        else:
            # Multi-option poll
            options_list = [opt.strip() for opt in options.split("|")]
            if len(options_list) > 10:
                await self._send_command_response(ctx, "❌ Maximum 10 options allowed.", ephemeral=True)
                return
                
            number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            description = [f"{number_emojis[i]} {option}" for i, option in enumerate(options_list)]
            
            embed = discord.Embed(
                title="📊 Poll",
                description=f"**{question}**\n\n" + "\n".join(description),
                color=discord.Color.blue(),
                timestamp=utcnow()
            )
            embed.set_footer(text=f"Asked by {ctx.author.display_name}")
            
            msg = await self._send_command_response(ctx, embed=embed)
            if isinstance(msg, discord.Message):
                reaction_set = set()
                for i in range(len(options_list)):
                    await msg.add_reaction(number_emojis[i])
                    reaction_set.add(number_emojis[i])
                self._poll_reaction_whitelist[msg.id] = reaction_set
        
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="invites", description="List active server invites")
    @commands.has_permissions(manage_guild=True)
    async def invites(self, ctx):
        """List all active invites for the server."""
        try:
            invites = await ctx.guild.invites()
            
            if not invites:
                await self._send_command_response(ctx, "No active invites found.")
                return
            
            # Group invites by creator
            invites_by_creator = {}
            for invite in invites:
                creator = invite.inviter
                if creator not in invites_by_creator:
                    invites_by_creator[creator] = []
                invites_by_creator[creator].append(invite)
            
            embed = discord.Embed(
                title="🔗 Server Invites",
                color=discord.Color.blue(),
                timestamp=utcnow()
            )
            
            for creator, user_invites in invites_by_creator.items():
                invite_list = []
                for invite in user_invites:
                    uses = f"{invite.uses or 0}/{invite.max_uses if invite.max_uses else '∞'}"
                    expires = "Never" if not invite.expires_at else format_dt(invite.expires_at, 'R')
                    invite_list.append(f"• {invite.code} (Uses: {uses}, Expires: {expires})")
                
                embed.add_field(
                    name=f"Created by {creator.display_name}",
                    value="\n".join(invite_list) or "No active invites",
                    inline=False
                )
            
            await self._send_command_response(ctx, embed=embed)
        except discord.Forbidden:
            await self._send_command_response(ctx, "❌ I don't have permission to view invites.", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error fetching invites: {e}")
            await self._send_command_response(ctx, "❌ An error occurred while fetching invites.", ephemeral=True)
        
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="roles", description="List all server roles")
    async def roles(self, ctx):
        """List all roles in the server and their member counts."""
        roles = ctx.guild.roles[1:]  # Exclude @everyone
        roles.reverse()  # Show highest roles first
        
        embed = discord.Embed(
            title="📋 Server Roles",
            color=discord.Color.blue(),
            timestamp=utcnow()
        )
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for role in roles:
            member_count = len(role.members)
            line = f"{role.mention} - {member_count} member{'s' if member_count != 1 else ''}"
            line_length = len(line)
            
            if current_length + line_length > 1024:  # Discord field value limit
                chunks.append(current_chunk)
                current_chunk = [line]
                current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length
        
        if current_chunk:
            chunks.append(current_chunk)
        
        for i, chunk in enumerate(chunks, 1):
            name = f"Roles [{len(roles)} total]" if i == 1 else f"Roles (continued)"
            embed.add_field(
                name=name,
                value="\n".join(chunk),
                inline=False
            )
        
        await self._send_command_response(ctx, embed=embed)
        await self.delete_command_message(ctx)

    @commands.hybrid_command(name="emojis", description="List all server emojis")
    async def emojis(self, ctx):
        """List all custom emojis in the server."""
        emojis = ctx.guild.emojis
        
        if not emojis:
            await self._send_command_response(ctx, "This server has no custom emojis.")
            await self.delete_command_message(ctx)
            return
        
        embed = discord.Embed(
            title="😀 Server Emojis",
            color=discord.Color.blue(),
            timestamp=utcnow()
        )
        
        # Split emojis into animated and static
        animated = [e for e in emojis if e.animated]
        static = [e for e in emojis if not e.animated]
        
        def chunk_emojis(emoji_list, chunk_size=25):
            """Split emoji list into chunks to fit within field limits."""
            for i in range(0, len(emoji_list), chunk_size):
                yield emoji_list[i:i + chunk_size]
        
        if static:
            for i, chunk in enumerate(chunk_emojis(static), 1):
                name = f"Static Emojis [{len(static)} total]" if i == 1 else "Static Emojis (continued)"
                value = " ".join(str(e) for e in chunk)
                embed.add_field(name=name, value=value or "None", inline=False)
        
        if animated:
            for i, chunk in enumerate(chunk_emojis(animated), 1):
                name = f"Animated Emojis [{len(animated)} total]" if i == 1 else "Animated Emojis (continued)"
                value = " ".join(str(e) for e in chunk)
                embed.add_field(name=name, value=value or "None", inline=False)
        
        embed.set_footer(text=f"Total Emojis: {len(emojis)} ({len(static)} static, {len(animated)} animated)")
        
        await self._send_command_response(ctx, embed=embed)
        await self.delete_command_message(ctx)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(UtilityCog(bot))
