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
from discord.ext.commands import MemberNotFound
from discord import app_commands
from discord.utils import utcnow, format_dt
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class EmbedModal(discord.ui.Modal, title='Create Custom Embed'):
    """Modal for creating custom embeds with proper formatting."""
    
    def __init__(self, temp_message=None):
        super().__init__()
        self.temp_message = temp_message
        
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
                
        # Send embed through webhook for complete silence
        try:
            webhooks = await interaction.channel.webhooks()
            webhook = None
            
            # Look for existing bot webhook
            for wh in webhooks:
                if wh.name == "Silent Embed Bot":
                    webhook = wh
                    break
            
            # Create webhook if none exists
            if webhook is None:
                webhook = await interaction.channel.create_webhook(name="Silent Embed Bot")
            
            # Send embed through webhook (completely silent)
            await webhook.send(
                embed=embed,
                username=interaction.client.user.display_name,
                avatar_url=interaction.client.user.display_avatar.url
            )
            
            # Send invisible response to close the modal
            await interaction.response.send_message("✅", ephemeral=True, delete_after=1)
            
        except discord.Forbidden:
            # Fallback to normal response if webhook fails
            await interaction.response.send_message(embed=embed)
        
        # Delete the temporary message after a short delay
        if self.temp_message:
            try:
                await self.temp_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or can't be deleted


class UtilityCog(commands.Cog):
    """Utility commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = utcnow()

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx: commands.Context):
        """Check the bot's latency."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms")

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx: commands.Context):
        """Check the bot's uptime."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        uptime_duration = utcnow() - self.bot.boot_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        await ctx.send(f"⏰ Bot uptime: `{uptime_str}`", ephemeral=True)

    @commands.command(name="embed", description="Create a silent embed message")
    @commands.has_permissions(manage_messages=True)
    async def embed_command(self, ctx: commands.Context):
        """Create a completely silent embed using modal popup."""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        # Send a temporary message that will be used to trigger the modal
        temp_msg = await ctx.send("📝")
        
        # Create the view and edit the message to show the button
        view = EmbedFormView(temp_msg)
        await temp_msg.edit(content="Click to create embed:", view=view)
    
    @commands.command(name="embedform", aliases=['eform'], description="Create an embed using modal form")
    @commands.has_permissions(manage_messages=True)
    async def embed_form_command(self, ctx: commands.Context):
        """Create a custom embed message using a modal popup form."""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        # Send a temporary message that will be edited to show the modal
        temp_msg = await ctx.send("Opening embed creator...")
        
        # Create the view and edit the message to show the button
        view = EmbedFormView(temp_msg)
        embed = discord.Embed(
            title="📝 Embed Form Creator", 
            description="Click the button below to open the form interface.",
            color=discord.Color.green()
        )
        await temp_msg.edit(content=None, embed=embed, view=view)
    
    @commands.command(name="quickembed", aliases=['qembed'], description="Create a quick embed with inline syntax")
    @commands.has_permissions(manage_messages=True)
    async def quick_embed_command(self, ctx: commands.Context, *, content: str = None):
        """Create a quick embed message. Usage: !quickembed [title] | [description] | [color] | [author] | [author_icon]"""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        if content is None:
            # Send simple usage message
            embed = discord.Embed(
                title="⚡ Quick Embed Creator",
                description="**Usage:** `!quickembed [title] | [description] | [color] | [author] | [author_icon]`\n\n"
                           "**Examples:**\n"
                           "`!quickembed Welcome! | This is a welcome message | blue`\n"
                           "`!quickembed | Just a description with no title | #ff0000`\n"
                           "`!quickembed Rules | Server rules here | green | Staff Team | https://example.com/icon.png`\n\n"
                           "**Tips:**\n"
                           "• Use `|` to separate different parts\n"
                           "• Leave parts empty but keep the `|` separators\n"
                           "• Colors: hex (#ff0000) or names (red, blue, green, etc.)\n"
                           "• Author icon must be a valid image URL\n"
                           "• Use `!embed` for the form interface",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, delete_after=30)
            return
        
        # Parse the content
        parts = [part.strip() for part in content.split('|')]
        
        # Pad parts list to ensure we have all possible parts
        while len(parts) < 5:
            parts.append('')
        
        title = parts[0] if parts[0] else None
        description = parts[1] if parts[1] else None
        color_str = parts[2] if parts[2] else 'blue'
        author_name = parts[3] if parts[3] else None
        author_icon = parts[4] if parts[4] else None
        
        # Validate input
        if not title and not description:
            await ctx.send("❌ You must provide at least a title or description for the embed.", delete_after=10)
            return
        
        # Create embed
        embed = discord.Embed()
        
        if title:
            embed.title = title
        if description:
            embed.description = description
        
        # Set color
        try:
            if color_str.startswith('#'):
                embed.color = discord.Color(int(color_str[1:], 16))
            elif hasattr(discord.Color, color_str.lower()):
                embed.color = getattr(discord.Color, color_str.lower())()
            else:
                embed.color = discord.Color(int(color_str, 16))
        except (ValueError, AttributeError):
            embed.color = discord.Color.blue()
        
        # Set author
        if author_name:
            try:
                if author_icon:
                    embed.set_author(name=author_name, icon_url=author_icon)
                else:
                    embed.set_author(name=author_name)
            except:
                embed.set_author(name=author_name)
        
        # Send the embed
        await ctx.send(embed=embed)


class EmbedFormView(discord.ui.View):
    """View for the embed form button."""
    
    def __init__(self, message=None):
        super().__init__(timeout=60)
        self.message = message
    
    @discord.ui.button(label='Create Embed', style=discord.ButtonStyle.primary, emoji='📝')
    async def create_embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need `manage_messages` permission to use this command.", ephemeral=True)
            return
        
        modal = EmbedModal(self.message)
        await interaction.response.send_modal(modal)
    
    async def on_timeout(self):
        # Delete the message when the view times out
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or can't be deleted


class EmbedFormView(discord.ui.View):
    """View for the embed form button."""
    
    def __init__(self, message=None):
        super().__init__(timeout=60)
        self.message = message
    
    @discord.ui.button(label='Create Embed', style=discord.ButtonStyle.primary, emoji='📝')
    async def create_embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need `manage_messages` permission to use this command.", ephemeral=True)
            return
        
        modal = EmbedModal(self.message)
        await interaction.response.send_modal(modal)
    
    async def on_timeout(self):
        # Delete the message when the view times out
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or can't be deleted


class UtilityCog(commands.Cog):
    """Utility commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = utcnow()

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx: commands.Context):
        """Check the bot's latency."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: {latency}ms")

    @commands.hybrid_command(name="uptime", description="Check bot's uptime")
    async def uptime(self, ctx: commands.Context):
        """Check the bot's uptime."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        uptime_duration = utcnow() - self.bot.boot_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        await ctx.send(f"⏰ Bot uptime: `{uptime_str}`", ephemeral=True)

    @commands.command(name="embed", description="Create a silent embed message")
    @commands.has_permissions(manage_messages=True)
    async def embed_command(self, ctx: commands.Context):
        """Create a completely silent embed using modal popup."""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        # Send a temporary message that will be used to trigger the modal
        temp_msg = await ctx.send("📝")
        
        # Create the view and edit the message to show the button
        view = EmbedFormView(temp_msg)
        await temp_msg.edit(content="Click to create embed:", view=view)
    
    @commands.command(name="embedform", aliases=['eform'], description="Create an embed using modal form")
    @commands.has_permissions(manage_messages=True)
    async def embed_form_command(self, ctx: commands.Context):
        """Create a custom embed message using a modal popup form."""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        # Send a temporary message that will be edited to show the modal
        temp_msg = await ctx.send("Opening embed creator...")
        
        # Create the view and edit the message to show the button
        view = EmbedFormView(temp_msg)
        embed = discord.Embed(
            title="📝 Embed Form Creator", 
            description="Click the button below to open the form interface.",
            color=discord.Color.green()
        )
        await temp_msg.edit(content=None, embed=embed, view=view)
    
    @commands.command(name="quickembed", aliases=['qembed'], description="Create a quick embed with inline syntax")
    @commands.has_permissions(manage_messages=True)
    async def quick_embed_command(self, ctx: commands.Context, *, content: str = None):
        """Create a quick embed message. Usage: !quickembed [title] | [description] | [color] | [author] | [author_icon]"""
        # Delete command message immediately
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        if content is None:
            # Send simple usage message
            embed = discord.Embed(
                title="⚡ Quick Embed Creator",
                description="**Usage:** `!quickembed [title] | [description] | [color] | [author] | [author_icon]`\n\n"
                           "**Examples:**\n"
                           "`!quickembed Welcome! | This is a welcome message | blue`\n"
                           "`!quickembed | Just a description with no title | #ff0000`\n"
                           "`!quickembed Rules | Server rules here | green | Staff Team | https://example.com/icon.png`\n\n"
                           "**Tips:**\n"
                           "• Use `|` to separate different parts\n"
                           "• Leave parts empty but keep the `|` separators\n"
                           "• Colors: hex (#ff0000) or names (red, blue, green, etc.)\n"
                           "• Author icon must be a valid image URL\n"
                           "• Use `!embed` for the form interface",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, delete_after=30)
            return
        
        # Parse the content
        parts = [part.strip() for part in content.split('|')]
        
        # Pad parts list to ensure we have all possible parts
        while len(parts) < 5:
            parts.append('')
        
        title = parts[0] if parts[0] else None
        description = parts[1] if parts[1] else None
        color_str = parts[2] if parts[2] else 'blue'
        author_name = parts[3] if parts[3] else None
        author_icon = parts[4] if parts[4] else None
        
        # Validate input
        if not title and not description:
            await ctx.send("❌ You must provide at least a title or description for the embed.", delete_after=10)
            return
        
        # Create embed
        embed = discord.Embed()
        
        if title:
            embed.title = title
        if description:
            embed.description = description
        
        # Set color
        try:
            if color_str.startswith('#'):
                embed.color = discord.Color(int(color_str[1:], 16))
            elif hasattr(discord.Color, color_str.lower()):
                embed.color = getattr(discord.Color, color_str.lower())()
            else:
                embed.color = discord.Color(int(color_str, 16))
        except (ValueError, AttributeError):
            embed.color = discord.Color.blue()
        
        # Set author
        if author_name:
            try:
                if author_icon:
                    embed.set_author(name=author_name, icon_url=author_icon)
                else:
                    embed.set_author(name=author_name)
            except:
                embed.set_author(name=author_name)
        
        # Send the embed
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo",
                             description="Get information about a user")
    @app_commands.describe(
        user="User to get info about (mention, ID, or username)")
    async def userinfo(self, ctx: commands.Context,
                       user: Optional[str] = None):
        """Get information about a user."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        # Determine target user
        target = None
        is_member = False

        if user is None:
            # Default to command author
            target = ctx.author
            is_member = isinstance(ctx.author, discord.Member)
        else:
            # Try to resolve the user
            # First, try to get as member if they're in the server
            try:
                # Try member converter for users in server
                member_converter = commands.MemberConverter()
                target = await member_converter.convert(ctx, user)
                is_member = True
            except (commands.BadArgument, MemberNotFound):
                # User not in server, try to get as user by ID
                try:
                    if user.isdigit():
                        target = await self.bot.fetch_user(int(user))
                        is_member = False
                    elif user.startswith('<@') and user.endswith('>'):
                        user_id = int(user.strip('<@!>'))
                        target = await self.bot.fetch_user(user_id)
                        is_member = False
                    else:
                        # Check if it's a username of someone in the server
                        if ctx.guild:
                            for member in ctx.guild.members:
                                if (member.name.lower() == user.lower() or
                                        member.display_name.lower() == user.lower()):
                                    target = member
                                    is_member = True
                                    break

                        if not target:
                            error_msg = (
                                "❌ User not found. Please provide a valid "
                                "user mention, ID, or username of someone "
                                "in this server.")
                            if ctx.interaction:
                                await ctx.send(error_msg, ephemeral=True)
                            else:
                                response = await ctx.send(error_msg)
                                await response.delete(delay=5)
                            return

                except (discord.NotFound, discord.HTTPException, ValueError):
                    error_msg = (
                        "❌ User not found or unable to fetch user "
                        "information.")
                    if ctx.interaction:
                        await ctx.send(error_msg, ephemeral=True)
                    else:
                        response = await ctx.send(error_msg)
                        await response.delete(delay=5)
                    return

        if not target:
            error_msg = "❌ Could not resolve user."
            if ctx.interaction:
                await ctx.send(error_msg, ephemeral=True)
            else:
                response = await ctx.send(error_msg)
                await response.delete(delay=5)
            return

        # Create embed with user information
        display_name = getattr(target, 'display_name', target.name)
        embed = discord.Embed(
            title=f"User Info - {display_name}",
            color=getattr(target, 'color', discord.Color.blue()),
            timestamp=utcnow()
        )

        embed.set_thumbnail(url=target.display_avatar.url)

        # Basic user info
        display_name_value = getattr(target, 'display_name', target.name)
        embed.add_field(
            name="User Info",
            value=f"**Username:** {target}\n"
                  f"**Display Name:** {display_name_value}\n"
                  f"**ID:** {target.id}\n"
                  f"**Bot:** {'Yes' if target.bot else 'No'}\n"
                  f"**In Server:** {'Yes' if is_member else 'No'}",
            inline=True
        )

        # Date information
        date_info = f"**Created:** {format_dt(target.created_at, 'R')}"
        if is_member and hasattr(target, 'joined_at') and target.joined_at:
            date_info += f"\n**Joined:** {format_dt(target.joined_at, 'R')}"
        elif is_member:
            date_info += "\n**Joined:** Unknown"

        embed.add_field(
            name="Dates",
            value=date_info,
            inline=True
        )

        # Role information (only for server members)
        if is_member and hasattr(target, 'roles') and len(target.roles) > 1:
            roles = [role.mention for role in target.roles[1:]]  # Exclude @everyone
            role_text = " ".join(roles) if len(" ".join(roles)) <= 1024 else f"{len(roles)} roles"
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=role_text,
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Get information about this server")
    async def serverinfo(self, ctx: commands.Context):
        """Get information about the server."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
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
    @app_commands.describe(
        user="User to get avatar of",
        size="Avatar size (16, 32, 64, 128, 256, 512, 1024, 2048, 4096) - default: 1024"
    )
    async def avatar(self, ctx: commands.Context, user: Optional[discord.Member] = None, size: Optional[int] = 1024):
        """Get a user's avatar."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        target = user or ctx.author
        
        # Validate size
        valid_sizes = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
        avatar_size = size if size in valid_sizes else 1024
        
        embed = discord.Embed(
            title=f"{target.display_name}'s Avatar ({avatar_size}x{avatar_size})",
            color=target.color,
            timestamp=utcnow()
        )

        # Prefer GIF for animated avatars
        if target.display_avatar.is_animated():
            avatar_url = target.display_avatar.replace(format='gif', size=avatar_size).url
            embed.set_image(url=avatar_url)
            embed.add_field(
                name="Links",
                value=f"[GIF]({avatar_url}) | [PNG]({target.display_avatar.replace(format='png', size=avatar_size).url}) | "
                      f"[JPG]({target.display_avatar.replace(format='jpg', size=avatar_size).url}) | "
                      f"[WEBP]({target.display_avatar.replace(format='webp', size=avatar_size).url})",
                inline=False
            )
        else:
            avatar_url = target.display_avatar.replace(size=avatar_size).url
            embed.set_image(url=avatar_url)
            embed.add_field(
                name="Links",
                value=f"[PNG]({target.display_avatar.replace(format='png', size=avatar_size).url}) | "
                      f"[JPG]({target.display_avatar.replace(format='jpg', size=avatar_size).url}) | "
                      f"[WEBP]({target.display_avatar.replace(format='webp', size=avatar_size).url})",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="av", description="Get a user's avatar (short version)", aliases=["pfp"])
    @app_commands.describe(
        user="User to get avatar of",
        format="Image format (png, jpg, webp, gif) - default: png"
    )
    async def av(self, ctx: commands.Context, user: Optional[discord.Member] = None, format: Optional[str] = "png"):
        """Get a user's avatar (short version with format option)."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        target = user or ctx.author
        
        # Validate format
        valid_formats = ["png", "jpg", "jpeg", "webp", "gif"]
        img_format = format.lower() if format.lower() in valid_formats else "png"
        
        # Prefer GIF for animated avatars if available
        if target.display_avatar.is_animated():
            avatar_url = target.display_avatar.replace(format='gif', size=1024).url
            embed = discord.Embed(
                title=f"{target.display_name}'s Avatar (GIF)",
                color=target.color,
                url=avatar_url
            )
            embed.set_image(url=avatar_url)
        else:
            # Get avatar URL in specified format
            if img_format == "gif":
                img_format = "png"  # Fallback for non-animated avatars
            avatar_url = target.display_avatar.replace(format=img_format, size=1024).url
            embed = discord.Embed(
                title=f"{target.display_name}'s Avatar ({img_format.upper()})",
                color=target.color,
                url=avatar_url
            )
            embed.set_image(url=avatar_url)
        
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="cat", description="Get random cat images (1-5)")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @app_commands.describe(count="How many cats to fetch (1-5)")
    async def cat(self, ctx: commands.Context, count: Optional[int] = 1):
        """Get random cat images (1-5)."""
        # For slash commands, respond silently first
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        # Validate count parameter
        n = max(1, min(int(count or 1), 5))

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
                            # Use webhook for silent sending
                            try:
                                webhooks = await ctx.channel.webhooks()
                                webhook = None
                                
                                # Look for existing bot webhook
                                for wh in webhooks:
                                    if wh.name == "Silent Cat Bot":
                                        webhook = wh
                                        break
                                
                                # Create webhook if none exists
                                if webhook is None:
                                    webhook = await ctx.channel.create_webhook(name="Silent Cat Bot")
                                
                                # Send cat images through webhook (completely silent)
                                for item in data:
                                    cat_url = item.get("url")
                                    if cat_url:
                                        await webhook.send(
                                            content=cat_url,
                                            username=ctx.bot.user.display_name,
                                            avatar_url=ctx.bot.user.display_avatar.url
                                        )
                                        if len(data) > 1:
                                            await asyncio.sleep(0.5)  # Small delay between multiple cats
                                
                                # Send confirmation only for slash commands
                                if ctx.interaction:
                                    await ctx.interaction.followup.send(f"🐱 Sent {n} cat{'s' if n > 1 else ''}!", ephemeral=True)
                                
                            except discord.Forbidden:
                                # Fallback to normal send if webhook fails
                                for item in data:
                                    cat_url = item.get("url")
                                    if cat_url:
                                        await ctx.send(cat_url)  # Send only the image URL for cleaner look
                                        if len(data) > 1:
                                            await asyncio.sleep(0.5)  # Small delay between multiple cats
                            return
                    else:
                        error_msg = f"❌ Cat API error: HTTP {response.status}"
                        if ctx.interaction:
                            await ctx.interaction.followup.send(error_msg, ephemeral=True)
                        else:
                            await ctx.send(error_msg, ephemeral=True)
                        return

        except asyncio.TimeoutError:
            error_msg = "❌ Cat API request timed out. Please try again later!"
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, ephemeral=True)
        except Exception as e:
            error_msg = f"❌ Failed to fetch cats: {str(e)}"
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, ephemeral=True)

    @commands.hybrid_command(name="dog", description="Get a random dog image")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def dog(self, ctx: commands.Context):
        """Get a random dog image."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
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

    @commands.hybrid_command(name="announce", description="Send an announcement")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        message="The announcement message (required)",
        channel="Channel to send announcement to (optional - defaults to current channel)",
        role="Role to ping (optional)",
        title="Title for the announcement (optional)"
    )
    async def announce(self, ctx: commands.Context, *, message: str, channel: Optional[discord.TextChannel] = None, role: Optional[discord.Role] = None, title: Optional[str] = None):
        """Send a clean announcement like Dyno. Usage: !announce <message> [#channel] [role] [title]"""
        
        # For slash commands, respond silently first
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        # Use specified channel or current channel
        target_channel = channel or ctx.channel
        
        # Check if bot has permissions in target channel
        if not target_channel.permissions_for(ctx.guild.me).send_messages:
            error_msg = f"❌ I don't have permission to send messages in {target_channel.mention}"
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=10)
            return
        
        # Create the embed with the exact style from the image
        embed = discord.Embed(
            description=message,
            color=0x00ff00  # Bright green color like in the image
        )
        
        # Add title if provided
        if title:
            embed.title = title
        
        # Prepare content for role ping
        content = ""
        if role:
            content = role.mention
        
        # Send announcement through webhook for complete anonymity
        try:
            webhooks = await target_channel.webhooks()
            webhook = None
            
            # Look for existing bot webhook
            for wh in webhooks:
                if wh.name == "Silent Announcement Bot":
                    webhook = wh
                    break
            
            # Create webhook if none exists
            if webhook is None:
                webhook = await target_channel.create_webhook(name="Silent Announcement Bot")
            
            # Send announcement through webhook (completely silent)
            await webhook.send(
                content=content if role else None,
                embed=embed,
                username=ctx.bot.user.display_name,
                avatar_url=ctx.bot.user.display_avatar.url
            )
            
            # Send confirmation only for slash commands
            if ctx.interaction:
                if target_channel == ctx.channel:
                    await ctx.interaction.followup.send("✅ Announcement sent!", ephemeral=True)
                else:
                    await ctx.interaction.followup.send(f"✅ Announcement sent to {target_channel.mention}!", ephemeral=True)
            
        except discord.Forbidden:
            # Fallback to normal send if webhook fails
            if role:
                await target_channel.send(content=role.mention, embed=embed)
            else:
                await target_channel.send(embed=embed)
            if ctx.interaction:
                if target_channel == ctx.channel:
                    await ctx.interaction.followup.send("✅ Announcement sent (fallback method)!", ephemeral=True)
                else:
                    await ctx.interaction.followup.send(f"✅ Announcement sent to {target_channel.mention} (fallback method)!", ephemeral=True)
        except Exception as e:
            error_msg = f"❌ Failed to send announcement: {str(e)}"
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=10)

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="Your question for the 8-ball")
    async def eightball(self, ctx: commands.Context, *, question: str):
        """Ask the magic 8-ball a question."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes definitely.",
            "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
            "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
            "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        
        import random
        response = random.choice(responses)
        
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            color=discord.Color.purple()
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=response, inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="quote", description="Get an inspirational quote")
    async def quote(self, ctx: commands.Context):
        """Get a random inspirational quote."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        quotes = [
            ("The only way to do great work is to love what you do.", "Steve Jobs"),
            ("Life is what happens to you while you're busy making other plans.", "John Lennon"),
            ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
            ("It is during our darkest moments that we must focus to see the light.", "Aristotle"),
            ("The only impossible journey is the one you never begin.", "Tony Robbins"),
            ("Success is not final, failure is not fatal: it is the courage to continue that counts.", "Winston Churchill"),
            ("The way to get started is to quit talking and begin doing.", "Walt Disney"),
            ("Your limitation—it's only your imagination.", "Anonymous"),
            ("Push yourself, because no one else is going to do it for you.", "Anonymous"),
            ("Great things never come from comfort zones.", "Anonymous")
        ]
        
        import random
        quote_text, author = random.choice(quotes)
        
        embed = discord.Embed(
            title="💭 Quote of the Moment",
            description=f"*\"{quote_text}\"*\n\n— {author}",
            color=discord.Color.gold()
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roll", description="Roll dice")
    @app_commands.describe(dice="Dice notation (e.g., 1d6, 2d20, 3d8+5)")
    async def roll(self, ctx: commands.Context, *, dice: str = "1d6"):
        """Roll dice using standard notation (e.g., 1d6, 2d20, 3d8+5)."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        import re
        import random
        
        # Parse dice notation
        match = re.match(r'(\d+)d(\d+)(?:([+-])(\d+))?', dice.lower().replace(' ', ''))
        if not match:
            await ctx.send("❌ Invalid dice notation. Use format like: 1d6, 2d20, 3d8+5", ephemeral=True)
            return
        
        num_dice = int(match.group(1))
        num_sides = int(match.group(2))
        modifier_sign = match.group(3)
        modifier = int(match.group(4)) if match.group(4) else 0
        
        if num_dice > 20:
            await ctx.send("❌ Maximum 20 dice allowed.", ephemeral=True)
            return
        
        if num_sides > 1000:
            await ctx.send("❌ Maximum 1000 sides per die.", ephemeral=True)
            return
        
        # Roll the dice
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        total = sum(rolls)
        
        # Apply modifier
        if modifier_sign == '+':
            total += modifier
        elif modifier_sign == '-':
            total -= modifier
        
        # Create embed
        embed = discord.Embed(
            title="🎲 Dice Roll",
            color=discord.Color.red()
        )
        
        if num_dice <= 10:  # Show individual rolls if reasonable
            rolls_str = " + ".join(map(str, rolls))
            if modifier_sign and modifier:
                rolls_str += f" {modifier_sign} {modifier}"
            embed.add_field(name="Rolls", value=rolls_str, inline=False)
        
        embed.add_field(name="Total", value=str(total), inline=False)
        embed.set_footer(text=f"Rolled {dice}")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Flip a coin")
    async def coinflip(self, ctx: commands.Context):
        """Flip a coin - heads or tails."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        import random
        result = random.choice(["Heads", "Tails"])
        emoji = "🟡" if result == "Heads" else "🔘"
        
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"{emoji} **{result}**",
            color=discord.Color.gold() if result == "Heads" else discord.Color.dark_grey()
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="fact", description="Get a random interesting fact")
    async def fact(self, ctx: commands.Context):
        """Get a random interesting fact."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        facts = [
            "Honey never spoils. Archaeologists have found edible honey in ancient Egyptian tombs.",
            "A group of flamingos is called a 'flamboyance'.",
            "Octopuses have three hearts and blue blood.",
            "Bananas are berries, but strawberries aren't.",
            "A single cloud can weigh more than a million pounds.",
            "The shortest war in history lasted only 38-45 minutes.",
            "Dolphins have names for each other.",
            "There are more possible games of chess than atoms in the observable universe.",
            "Wombat poop is cube-shaped.",
            "A group of crows is called a 'murder'."
        ]
        
        import random
        fact = random.choice(facts)
        
        embed = discord.Embed(
            title="🧠 Random Fact",
            description=fact,
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="weather", description="Get weather information for a city or zip code")
    @app_commands.describe(location="City name or zip code (e.g., 'London' or '10001' or '10001,US')")
    async def weather(self, ctx: commands.Context, *, location: str):
        """Get weather information for a city or zip code."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if ctx.interaction:
            await ctx.defer()
        
        api_key = "89684fe6e72da07205a0d27f1b859442"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Determine if input is a zip code or city name
                location_param = self._format_location_for_api(location)
                
                # Get current weather
                url = f"http://api.openweathermap.org/data/2.5/weather?{location_param}&appid={api_key}&units=metric"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract weather data
                        temp = data['main']['temp']
                        feels_like = data['main']['feels_like']
                        humidity = data['main']['humidity']
                        pressure = data['main']['pressure']
                        description = data['weather'][0]['description'].title()
                        icon = data['weather'][0]['icon']
                        wind_speed = data['wind']['speed']
                        wind_deg = data['wind'].get('deg', 0)
                        
                        # Convert wind direction
                        def get_wind_direction(degrees):
                            directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
                            return directions[int((degrees + 11.25) / 22.5) % 16]
                        
                        wind_dir = get_wind_direction(wind_deg)
                        
                        # Create embed
                        embed = discord.Embed(
                            title=f"🌤️ Weather for {data['name']}, {data['sys']['country']}",
                            description=description,
                            color=discord.Color.blue()
                        )
                        
                        # Convert to Fahrenheit
                        temp_f = temp * 9/5 + 32
                        feels_like_f = feels_like * 9/5 + 32
                        
                        # Temperature info (Fahrenheit only)
                        embed.add_field(
                            name="🌡️ Temperature",
                            value=f"**{temp_f:.1f}°F** (feels like {feels_like_f:.1f}°F)",
                            inline=True
                        )
                        
                        # Humidity and Pressure
                        embed.add_field(
                            name="💧 Humidity & Pressure",
                            value=f"**Humidity:** {humidity}%\n**Pressure:** {pressure} hPa",
                            inline=True
                        )
                        
                        # Wind info
                        embed.add_field(
                            name="💨 Wind",
                            value=f"**Speed:** {wind_speed} m/s\n**Direction:** {wind_dir} ({wind_deg}°)",
                            inline=True
                        )
                        
                        # Visibility if available
                        if 'visibility' in data:
                            visibility_km = data['visibility'] / 1000
                            visibility_miles = visibility_km * 0.621371  # Convert to miles
                            embed.add_field(
                                name="👁️ Visibility",
                                value=f"{visibility_miles:.1f} miles",
                                inline=True
                            )
                        
                        await ctx.send(embed=embed)
                        
                    elif response.status == 404:
                        embed = discord.Embed(
                            title="❌ Location Not Found",
                            description=(
                                f"Could not find weather data for '{location}'. "
                                "Please check the spelling and try again.\n\n"
                                "**Supported formats:**\n"
                                "• City names: `London`, `New York`\n"
                                "• ZIP codes: `10001` (US), `10001,US`\n"
                                "• International postal codes: `SW1A 1AA,GB`"
                            ),
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed, ephemeral=True)
                    else:
                        await ctx.send(f"❌ Weather API error: HTTP {response.status}", ephemeral=True)
                        
        except asyncio.TimeoutError:
            await ctx.send("❌ Weather API request timed out. Please try again later!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch weather: {str(e)}", ephemeral=True)

    def _format_location_for_api(self, location: str) -> str:
        """Format location input for OpenWeatherMap API."""
        location = location.strip()
        
        # Check if it looks like a zip code (numeric, optionally with country code)
        if ',' in location:
            # Already has country code (e.g., "10001,US" or "SW1A 1AA,GB")
            return f"zip={location}"
        elif location.replace(' ', '').isdigit():
            # Numeric only - assume US zip code
            return f"zip={location},US"
        elif len(location) == 5 and location.isdigit():
            # 5-digit number - US zip code
            return f"zip={location},US"
        else:
            # Assume it's a city name
            return f"q={location}"

    @commands.command(name="poll", description="Create a poll with reactions")
    @commands.has_permissions(manage_messages=True)
    async def poll(self, ctx: commands.Context, question: str, *options):
        """Create a poll. Usage: !poll "Question?" "Option 1" "Option 2" ..."""
        # Delete command message
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        if len(options) < 2:
            await ctx.send("❌ You need at least 2 options for a poll.", delete_after=10)
            return
        
        if len(options) > 10:
            await ctx.send("❌ Maximum 10 options allowed.", delete_after=10)
            return
        
        # Emoji numbers for reactions
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=discord.Color.blue()
        )
        
        for i, option in enumerate(options):
            embed.add_field(name=f"{emojis[i]} Option {i+1}", value=option, inline=False)
        
        embed.set_footer(text=f"Poll created by {ctx.author.display_name}")
        
        poll_msg = await ctx.send(embed=embed)
        
        # Add reactions
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])

    @commands.hybrid_command(name="timestamp", description="Generate Discord timestamps")
    @app_commands.describe(
        time="Time in format: YYYY-MM-DD HH:MM or 'now'",
        format="Timestamp format (t, T, d, D, f, F, R)"
    )
    async def timestamp(self, ctx: commands.Context, time: str = "now", format: str = "f"):
        """Generate Discord timestamps."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        import datetime
        
        if time.lower() == "now":
            timestamp = int(datetime.datetime.now().timestamp())
        else:
            try:
                # Parse time string
                dt = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
                timestamp = int(dt.timestamp())
            except ValueError:
                await ctx.send("❌ Invalid time format. Use YYYY-MM-DD HH:MM or 'now'", ephemeral=True)
                return
        
        valid_formats = ["t", "T", "d", "D", "f", "F", "R"]
        if format not in valid_formats:
            format = "f"
        
        discord_timestamp = f"<t:{timestamp}:{format}>"
        
        embed = discord.Embed(
            title="🕒 Discord Timestamp",
            color=discord.Color.blue()
        )
        embed.add_field(name="Timestamp", value=discord_timestamp, inline=False)
        embed.add_field(name="Raw Code", value=f"`{discord_timestamp}`", inline=False)
        embed.add_field(
            name="Format Options",
            value="t - Short Time\nT - Long Time\nd - Short Date\nD - Long Date\nf - Short Date/Time\nF - Long Date/Time\nR - Relative Time",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="color", description="Show color preview from hex code")
    @app_commands.describe(hex_code="Hex color code (with or without #)")
    async def color(self, ctx: commands.Context, hex_code: str):
        """Show color preview from hex code."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        # Clean hex code
        hex_code = hex_code.replace("#", "").upper()
        
        try:
            # Validate hex code
            int(hex_code, 16)
            if len(hex_code) != 6:
                raise ValueError("Invalid length")
        except ValueError:
            await ctx.send("❌ Invalid hex color code. Use format: #FF0000 or FF0000", ephemeral=True)
            return
        
        # Convert to decimal for Discord color
        color_int = int(hex_code, 16)
        
        embed = discord.Embed(
            title=f"🎨 Color Preview",
            description=f"**Hex:** #{hex_code}\n**Decimal:** {color_int}",
            color=discord.Color(color_int)
        )
        
        # Add RGB values
        r = (color_int >> 16) & 255
        g = (color_int >> 8) & 255
        b = color_int & 255
        embed.add_field(name="RGB", value=f"({r}, {g}, {b})", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="slowmode", description="Set channel slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int = 0):
        """Set slowmode for the current channel."""
        # Delete command message
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        if seconds < 0 or seconds > 21600:  # Discord's max is 6 hours
            await ctx.send("❌ Slowmode must be between 0 and 21600 seconds (6 hours).", delete_after=10)
            return
        
        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            if seconds == 0:
                await ctx.send("✅ Slowmode disabled.", delete_after=5)
            else:
                await ctx.send(f"✅ Slowmode set to {seconds} seconds.", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to edit this channel.", delete_after=10)

    @commands.command(name="lock", description="Lock the current channel")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        """Lock the current channel."""
        # Delete command message
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
            await ctx.send("🔒 Channel locked.", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to lock this channel.", delete_after=10)

    @commands.command(name="unlock", description="Unlock the current channel")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        """Unlock the current channel."""
        # Delete command message
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
            await ctx.send("🔓 Channel unlocked.", delete_after=5)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to unlock this channel.", delete_after=10)

    @commands.hybrid_command(name="hug", description="Hug someone")
    @app_commands.describe(user="User to hug")
    async def hug(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Hug someone."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if not user:
            await ctx.send("❌ You need to mention someone to hug!", ephemeral=True)
            return
        
        if user == ctx.author:
            await ctx.send("🤗 You hug yourself! Self-love is important!")
            return
        
        embed = discord.Embed(
            description=f"🤗 {ctx.author.mention} hugs {user.mention}!",
            color=discord.Color.pink()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="pat", description="Pat someone")
    @app_commands.describe(user="User to pat")
    async def pat(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Pat someone."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if not user:
            await ctx.send("❌ You need to mention someone to pat!", ephemeral=True)
            return
        
        if user == ctx.author:
            await ctx.send("👋 You pat yourself on the head!")
            return
        
        embed = discord.Embed(
            description=f"👋 {ctx.author.mention} pats {user.mention} on the head!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="poke", description="Poke someone")
    @app_commands.describe(user="User to poke")
    async def poke(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Poke someone."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if not user:
            await ctx.send("❌ You need to mention someone to poke!", ephemeral=True)
            return
        
        if user == ctx.author:
            await ctx.send("👆 You poke yourself!")
            return
        
        embed = discord.Embed(
            description=f"👆 {ctx.author.mention} pokes {user.mention}!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ship", description="Ship two users with compatibility percentage")
    @app_commands.describe(user1="First user", user2="Second user")
    async def ship(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member = None):
        """Ship two users with compatibility percentage."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if user2 is None:
            user2 = ctx.author
        
        # Generate a "random" but consistent percentage based on user IDs
        import hashlib
        combined_id = str(min(user1.id, user2.id)) + str(max(user1.id, user2.id))
        hash_object = hashlib.md5(combined_id.encode())
        percentage = int(hash_object.hexdigest()[:2], 16) % 101  # 0-100
        
        # Create ship name
        name1 = user1.display_name[:len(user1.display_name)//2]
        name2 = user2.display_name[len(user2.display_name)//2:]
        ship_name = name1 + name2
        
        # Determine compatibility level
        if percentage >= 90:
            compatibility = "💕 Perfect Match!"
            color = discord.Color.red()
        elif percentage >= 70:
            compatibility = "💖 Great Match!"
            color = discord.Color.pink()
        elif percentage >= 50:
            compatibility = "💛 Good Match!"
            color = discord.Color.gold()
        elif percentage >= 30:
            compatibility = "💙 Okay Match"
            color = discord.Color.blue()
        else:
            compatibility = "💔 Not Compatible"
            color = discord.Color.dark_grey()
        
        embed = discord.Embed(
            title="💘 Love Calculator",
            color=color
        )
        embed.add_field(name="Ship Name", value=ship_name, inline=True)
        embed.add_field(name="Compatibility", value=f"{percentage}%", inline=True)
        embed.add_field(name="Result", value=compatibility, inline=True)
        embed.add_field(
            name="Couple",
            value=f"{user1.mention} + {user2.mention}",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="qr", description="Generate a QR code")
    @app_commands.describe(text="Text to encode in QR code")
    async def qr(self, ctx: commands.Context, *, text: str):
        """Generate a QR code for the given text."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if len(text) > 500:
            await ctx.send("❌ Text too long! Maximum 500 characters.", ephemeral=True)
            return
        
        # Using a free QR code API
        import urllib.parse
        encoded_text = urllib.parse.quote(text)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_text}"
        
        embed = discord.Embed(
            title="📱 QR Code Generated",
            description=f"**Text:** {text[:100]}{'...' if len(text) > 100 else ''}",
            color=discord.Color.blue()
        )
        embed.set_image(url=qr_url)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="github", description="Get GitHub repository information")
    @app_commands.describe(repo="Repository in format: owner/repo")
    async def github(self, ctx: commands.Context, repo: str):
        """Get GitHub repository information."""
        # Delete command message for prefix commands
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if ctx.interaction:
            await ctx.defer()
        
        if "/" not in repo:
            await ctx.send("❌ Please use format: owner/repo", ephemeral=True)
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.github.com/repos/{repo}", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        embed = discord.Embed(
                            title=f"📁 {data['full_name']}",
                            url=data['html_url'],
                            description=data.get('description', 'No description'),
                            color=discord.Color.dark_grey()
                        )
                        
                        embed.add_field(name="⭐ Stars", value=data['stargazers_count'], inline=True)
                        embed.add_field(name="🍴 Forks", value=data['forks_count'], inline=True)
                        embed.add_field(name="📝 Language", value=data.get('language', 'Unknown'), inline=True)
                        embed.add_field(name="📊 Size", value=f"{data['size']} KB", inline=True)
                        embed.add_field(name="🐛 Issues", value=data['open_issues_count'], inline=True)
                        embed.add_field(name="📅 Created", value=data['created_at'][:10], inline=True)
                        
                        if data.get('license'):
                            embed.add_field(name="📄 License", value=data['license']['name'], inline=True)
                        
                        await ctx.send(embed=embed)
                    elif response.status == 404:
                        await ctx.send("❌ Repository not found.", ephemeral=True)
                    else:
                        await ctx.send(f"❌ GitHub API error: HTTP {response.status}", ephemeral=True)
                        
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch repository info: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
