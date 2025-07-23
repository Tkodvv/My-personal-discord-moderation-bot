"""
Utility Cog
Contains utility commands like userinfo, avatar, server info, etc.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from typing import Optional

class UtilityCog(commands.Cog):
    """Utility commands cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.start_time = datetime.utcnow()
    
    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
    
    @app_commands.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(member="The member to get information about")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Get detailed information about a user."""
        if member is None:
            member = interaction.user
        
        # Ensure member is a Member, not User
        if isinstance(member, discord.User) and interaction.guild:
            member = interaction.guild.get_member(member.id)
            if not member:
                await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
                return
        
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ User information is only available for server members.", ephemeral=True)
            return
        
        # Create embed with user information
        embed = discord.Embed(
            title=f"User Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Set thumbnail to user avatar
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Basic information
        embed.add_field(name="Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        
        # Account creation date
        created_at = int(member.created_at.timestamp())
        embed.add_field(name="Account Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        
        # Server join date
        if member.joined_at:
            joined_at = int(member.joined_at.timestamp())
            embed.add_field(name="Joined Server", value=f"<t:{joined_at}:F> (<t:{joined_at}:R>)", inline=False)
        
        # Status and activity
        status_emoji = {
            discord.Status.online: "🟢",
            discord.Status.idle: "🟡",
            discord.Status.dnd: "🔴",
            discord.Status.offline: "⚫"
        }
        embed.add_field(name="Status", value=f"{status_emoji.get(member.status, '❓')} {member.status.name.title()}", inline=True)
        
        # Roles (excluding @everyone)
        roles = [role.mention for role in member.roles[1:]]
        if roles:
            roles_text = ", ".join(roles) if len(", ".join(roles)) <= 1024 else f"{len(roles)} roles"
            embed.add_field(name=f"Roles [{len(roles)}]", value=roles_text, inline=False)
        
        # Permissions
        if member.guild_permissions.administrator:
            embed.add_field(name="Permissions", value="Administrator", inline=True)
        elif any([
            member.guild_permissions.kick_members,
            member.guild_permissions.ban_members,
            member.guild_permissions.manage_messages,
            member.guild_permissions.manage_channels
        ]):
            embed.add_field(name="Permissions", value="Moderator", inline=True)
        
        # Boost status
        if member.premium_since:
            boost_since = int(member.premium_since.timestamp())
            embed.add_field(name="Boosting Since", value=f"<t:{boost_since}:F>", inline=True)
        
        # Timeout status
        if member.timed_out_until:
            timeout_until = int(member.timed_out_until.timestamp())
            embed.add_field(name="Timed Out Until", value=f"<t:{timeout_until}:F>", inline=True)
        
        # Set footer
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(member="The member to get the avatar of")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Get a user's avatar in high resolution."""
        if member is None:
            member = interaction.user
        
        # Ensure member is a Member, not User
        if isinstance(member, discord.User) and interaction.guild:
            member = interaction.guild.get_member(member.id)
            if not member:
                await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
                return
        
        # Create embed with avatar
        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Set the image to the user's avatar
        embed.set_image(url=member.display_avatar.url)
        
        # Add download links
        avatar_formats = []
        if member.display_avatar.is_animated():
            avatar_formats.append(f"[GIF]({member.display_avatar.replace(format='gif', size=1024).url})")
        avatar_formats.extend([
            f"[PNG]({member.display_avatar.replace(format='png', size=1024).url})",
            f"[JPG]({member.display_avatar.replace(format='jpg', size=1024).url})",
            f"[WEBP]({member.display_avatar.replace(format='webp', size=1024).url})"
        ])
        
        embed.add_field(name="Download Links", value=" | ".join(avatar_formats), inline=False)
        
        # Set footer
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, interaction: discord.Interaction):
        """Get detailed information about the server."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        
        # Create embed with server information
        embed = discord.Embed(
            title=f"Server Information - {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Set thumbnail to server icon
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Basic information
        embed.add_field(name="Server Name", value=guild.name, inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        
        # Creation date
        created_at = int(guild.created_at.timestamp())
        embed.add_field(name="Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        
        # Member counts
        total_members = guild.member_count
        online_members = sum(1 for member in guild.members if member.status != discord.Status.offline)
        embed.add_field(name="Members", value=f"Total: {total_members}\nOnline: {online_members}", inline=True)
        
        # Channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        embed.add_field(name="Channels", value=f"Text: {text_channels}\nVoice: {voice_channels}\nCategories: {categories}", inline=True)
        
        # Role count
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        
        # Boost information
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count or 0, inline=True)
        
        # Features
        if guild.features:
            features = [feature.replace('_', ' ').title() for feature in guild.features]
            features_text = ", ".join(features) if len(", ".join(features)) <= 1024 else f"{len(features)} features"
            embed.add_field(name="Features", value=features_text, inline=False)
        
        # Set footer
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        """Check the bot's latency."""
        # Calculate latency
        latency = round(self.bot.latency * 1000)
        
        # Create embed
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="roleinfo", description="Get information about a role")
    @app_commands.describe(role="The role to get information about")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        """Get detailed information about a role."""
        # Create embed with role information
        embed = discord.Embed(
            title=f"Role Information - {role.name}",
            color=role.color if role.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Basic information
        embed.add_field(name="Role Name", value=role.name, inline=True)
        embed.add_field(name="Role ID", value=role.id, inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        
        # Creation date
        created_at = int(role.created_at.timestamp())
        embed.add_field(name="Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        
        # Color and position
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        
        # Permissions
        if role.permissions.administrator:
            embed.add_field(name="Permissions", value="Administrator (All permissions)", inline=False)
        else:
            key_perms = []
            perm_checks = [
                ("Kick Members", role.permissions.kick_members),
                ("Ban Members", role.permissions.ban_members),
                ("Manage Messages", role.permissions.manage_messages),
                ("Manage Channels", role.permissions.manage_channels),
                ("Manage Server", role.permissions.manage_guild),
                ("Manage Roles", role.permissions.manage_roles),
                ("Mention Everyone", role.permissions.mention_everyone),
            ]
            
            for perm_name, has_perm in perm_checks:
                if has_perm:
                    key_perms.append(perm_name)
            
            if key_perms:
                embed.add_field(name="Key Permissions", value=", ".join(key_perms), inline=False)
        
        # Set footer
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="uptime", description="Show how long the bot has been running")
    async def uptime(self, interaction: discord.Interaction):
        """Show the bot's uptime."""
        uptime_duration = datetime.utcnow() - self.start_time
        
        # Calculate uptime components
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Format uptime string
        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            uptime_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            uptime_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not uptime_parts:
            uptime_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
        uptime_text = ", ".join(uptime_parts)
        
        # Create embed
        embed = discord.Embed(
            title="⏰ Bot Uptime",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Uptime", value=uptime_text, inline=False)
        embed.add_field(name="Started", value=f"<t:{int(self.start_time.timestamp())}:F>", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="joined", description="Show when a member joined the server")
    @app_commands.describe(member="The member to check join date for")
    async def joined(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Show when a member joined the server."""
        if member is None:
            member = interaction.user
        
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Join information is only available for server members.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"Join Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
        
        # Calculate days since joining
        days_since_join = (datetime.utcnow() - member.joined_at.replace(tzinfo=None)).days
        embed.add_field(name="Days in Server", value=f"{days_since_join} days", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="roles", description="Show all roles in the server or a specific member's roles")
    @app_commands.describe(member="The member to show roles for (optional)")
    async def roles(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Show server roles or a member's roles."""
        if member:
            # Show specific member's roles
            if len(member.roles) <= 1:  # @everyone role only
                embed = discord.Embed(
                    title=f"{member.display_name}'s Roles",
                    description="This member has no special roles.",
                    color=discord.Color.blue()
                )
            else:
                roles = [role.mention for role in reversed(member.roles[1:])]  # Skip @everyone
                embed = discord.Embed(
                    title=f"{member.display_name}'s Roles",
                    description="\n".join(roles),
                    color=member.color if member.color != discord.Color.default() else discord.Color.blue()
                )
                embed.add_field(name="Role Count", value=len(member.roles) - 1, inline=True)
        else:
            # Show all server roles
            guild_roles = [role for role in reversed(interaction.guild.roles[1:])]  # Skip @everyone
            if not guild_roles:
                embed = discord.Embed(
                    title=f"{interaction.guild.name} Roles",
                    description="This server has no special roles.",
                    color=discord.Color.blue()
                )
            else:
                roles_text = "\n".join([f"{role.mention} - {len(role.members)} members" for role in guild_roles[:20]])  # Limit to 20
                if len(guild_roles) > 20:
                    roles_text += f"\n... and {len(guild_roles) - 20} more roles"
                
                embed = discord.Embed(
                    title=f"{interaction.guild.name} Roles",
                    description=roles_text,
                    color=discord.Color.blue()
                )
                embed.add_field(name="Total Roles", value=len(guild_roles), inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="whois", description="Detailed information about a user")
    @app_commands.describe(user="The user to get information about")
    async def whois(self, interaction: discord.Interaction, user: discord.User):
        """Get detailed information about a user."""
        embed = discord.Embed(
            title=f"User Information - {user.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Basic info
        embed.add_field(name="Username", value=f"{user.name}#{user.discriminator}", inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
        
        # If it's a member of this guild, add more info
        if isinstance(user, discord.Member):
            embed.add_field(name="Joined", value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)
            embed.add_field(name="Status", value=user.status.name.title(), inline=True)
            embed.add_field(name="Top Role", value=user.top_role.mention, inline=True)
            embed.add_field(name="Role Count", value=len(user.roles) - 1, inline=True)
            
            if user.premium_since:
                embed.add_field(name="Boosting Since", value=f"<t:{int(user.premium_since.timestamp())}:F>", inline=False)
        
        embed.add_field(name="Bot Account", value="Yes" if user.bot else "No", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stats", description="Show server statistics")
    async def stats(self, interaction: discord.Interaction):
        """Show detailed server statistics."""
        guild = interaction.guild
        
        # Count members by status
        online = sum(1 for member in guild.members if member.status == discord.Status.online)
        idle = sum(1 for member in guild.members if member.status == discord.Status.idle)
        dnd = sum(1 for member in guild.members if member.status == discord.Status.dnd)
        offline = sum(1 for member in guild.members if member.status == discord.Status.offline)
        
        # Count channels
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        # Count bots vs humans
        bots = sum(1 for member in guild.members if member.bot)
        humans = guild.member_count - bots
        
        embed = discord.Embed(
            title=f"{guild.name} Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        # Member stats
        embed.add_field(
            name="👥 Members",
            value=f"Total: {guild.member_count}\nHumans: {humans}\nBots: {bots}",
            inline=True
        )
        
        # Status stats
        embed.add_field(
            name="📊 Status",
            value=f"🟢 Online: {online}\n🟡 Idle: {idle}\n🔴 DND: {dnd}\n⚫ Offline: {offline}",
            inline=True
        )
        
        # Channel stats
        embed.add_field(
            name="📋 Channels",
            value=f"Text: {text_channels}\nVoice: {voice_channels}\nCategories: {categories}",
            inline=True
        )
        
        # Server info
        embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=False)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
        
        if guild.premium_subscription_count:
            embed.add_field(name="💎 Boosts", value=f"{guild.premium_subscription_count} (Level {guild.premium_tier})", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    # Prefix command versions (auto-delete)
    @commands.command(name="userinfo", aliases=["ui"])
    async def prefix_userinfo(self, ctx, member: Optional[discord.Member] = None):
        """Prefix version of userinfo command."""
        await self.delete_command_message(ctx)
        
        if member is None:
            member = ctx.author
        
        if not isinstance(member, discord.Member):
            await ctx.send("❌ User information is only available for server members.", delete_after=5)
            return
        
        embed = discord.Embed(
            title=f"User Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Status", value=member.status.name.title(), inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="avatar", aliases=["av"])
    async def prefix_avatar(self, ctx, member: Optional[discord.Member] = None):
        """Prefix version of avatar command."""
        await self.delete_command_message(ctx)
        
        if member is None:
            member = ctx.author
        
        if not isinstance(member, discord.Member):
            await ctx.send("❌ Avatar information is only available for server members.", delete_after=5)
            return
        
        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)
    
    @commands.command(name="ping")
    async def prefix_ping(self, ctx):
        """Prefix version of ping command."""
        await self.delete_command_message(ctx)
        
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        await ctx.send(embed=embed)

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(UtilityCog(bot))
