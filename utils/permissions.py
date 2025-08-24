"""
Permission Utilities
Helper functions for checking permissions and role hierarchy.
"""

import discord
from typing import Union, Optional
from discord.ext import commands

def has_moderation_permissions(moderator: discord.Member, target: discord.Member) -> bool:
    """
    Check if a moderator has permission to moderate a target member.
    
    Args:
        moderator: The member performing the moderation action
        target: The member being moderated
    
    Returns:
        bool: True if moderator can moderate target, False otherwise
    """
    # Can't moderate yourself
    if moderator == target:
        return False
    
    # Can't moderate the server owner
    if target == target.guild.owner:
        return False
    
    # Server owner can moderate anyone
    if moderator == moderator.guild.owner:
        return True
    
    # Check if moderator has required permissions
    if not any([
        moderator.guild_permissions.kick_members,
        moderator.guild_permissions.ban_members,
        moderator.guild_permissions.moderate_members,
        moderator.guild_permissions.administrator
    ]):
        return False
    
    # Check role hierarchy
    return moderator.top_role > target.top_role

def has_higher_role(bot_member: discord.Member, target: discord.Member) -> bool:
    """
    Check if the bot has a higher role than the target member.
    
    Args:
        bot_member: The bot's member object
        target: The target member
    
    Returns:
        bool: True if bot can moderate target, False otherwise
    """
    # Can't moderate the server owner
    if target == target.guild.owner:
        return False
    
    # Check role hierarchy
    return bot_member.top_role > target.top_role

def can_execute_command(user: discord.Member, command_name: str) -> bool:
    """
    Check if a user can execute a specific command based on their permissions.
    
    Args:
        user: The user trying to execute the command
        command_name: Name of the command
    
    Returns:
        bool: True if user can execute command, False otherwise
    """
    permission_map = {
        'kick': user.guild_permissions.kick_members,
        'ban': user.guild_permissions.ban_members,
        'unban': user.guild_permissions.ban_members,
        'timeout': user.guild_permissions.moderate_members,
        'untimeout': user.guild_permissions.moderate_members,
    }
    
    # Administrator can do everything
    if user.guild_permissions.administrator:
        return True
    
    # Check specific permission for command
    return permission_map.get(command_name, True)

def format_permissions(permissions: discord.Permissions) -> list:
    """
    Format Discord permissions into a readable list.
    
    Args:
        permissions: Discord permissions object
    
    Returns:
        list: List of permission names that are True
    """
    perm_list = []
    
    # Define important permissions to check
    important_perms = [
        ('Administrator', permissions.administrator),
        ('Manage Server', permissions.manage_guild),
        ('Manage Roles', permissions.manage_roles),
        ('Manage Channels', permissions.manage_channels),
        ('Kick Members', permissions.kick_members),
        ('Ban Members', permissions.ban_members),
        ('Moderate Members', permissions.moderate_members),
        ('Manage Messages', permissions.manage_messages),
        ('Mention Everyone', permissions.mention_everyone),
        ('View Audit Log', permissions.view_audit_log),
        ('Manage Webhooks', permissions.manage_webhooks),
        ('Manage Emojis', permissions.manage_emojis_and_stickers),
    ]
    
    for perm_name, has_perm in important_perms:
        if has_perm:
            perm_list.append(perm_name)
    
    return perm_list

def check_bot_permissions(guild: discord.Guild, required_permissions: list) -> tuple:
    """
    Check if the bot has required permissions in a guild.
    
    Args:
        guild: The guild to check permissions in
        required_permissions: List of permission names to check
    
    Returns:
        tuple: (has_all_permissions: bool, missing_permissions: list)
    """
    bot_member = guild.me
    bot_permissions = bot_member.guild_permissions
    
    permission_attrs = {
        'kick_members': bot_permissions.kick_members,
        'ban_members': bot_permissions.ban_members,
        'moderate_members': bot_permissions.moderate_members,
        'manage_messages': bot_permissions.manage_messages,
        'manage_roles': bot_permissions.manage_roles,
        'manage_channels': bot_permissions.manage_channels,
        'view_audit_log': bot_permissions.view_audit_log,
        'send_messages': bot_permissions.send_messages,
        'embed_links': bot_permissions.embed_links,
        'read_message_history': bot_permissions.read_message_history,
    }
    
    missing = []
    for perm in required_permissions:
        if perm in permission_attrs and not permission_attrs[perm]:
            missing.append(perm)
    
    return len(missing) == 0, missing


def is_mod_whitelisted(member: discord.Member, bot) -> bool:
    """
    Check if a member has mod whitelist permissions via their roles or user ID.
    
    Args:
        member: The member to check
        bot: The bot instance with mod_whitelist and mod_whitelist_users
    
    Returns:
        bool: True if member has mod permissions via whitelist
    """
    # Check role-based whitelist
    if hasattr(bot, 'mod_whitelist') and bot.mod_whitelist:
        guild_whitelist = bot.mod_whitelist.get(str(member.guild.id), [])
        if guild_whitelist:
            # Check if any of the member's roles are in the whitelist
            member_role_ids = [role.id for role in member.roles]
            if any(role_id in guild_whitelist for role_id in member_role_ids):
                return True
    
    # Check user-based whitelist
    if hasattr(bot, 'mod_whitelist_users') and bot.mod_whitelist_users:
        guild_user_whitelist = bot.mod_whitelist_users.get(
            str(member.guild.id), [])
        if member.id in guild_user_whitelist:
            return True
    
    return False


def has_mod_permissions(member: discord.Member, bot,
                        required_discord_perm: Optional[str] = None) -> bool:
    """
    Check if member has mod permissions via Discord perms OR mod whitelist.
    
    Args:
        member: The member to check
        bot: The bot instance
        required_discord_perm: Discord permission name to check
    
    Returns:
        bool: True if member has required permissions
    """
    # Always allow administrators
    if member.guild_permissions.administrator:
        return True
    
    # Check specific Discord permission if provided
    if required_discord_perm:
        discord_perm = getattr(member.guild_permissions,
                               required_discord_perm, False)
        if discord_perm:
            return True
    
    # Check mod whitelist
    return is_mod_whitelisted(member, bot)


def mod_check(required_discord_perm: Optional[str] = None):
    """
    Decorator factory for creating custom permission checks.
    
    Args:
        required_discord_perm: Discord permission name
    
    Returns:
        Command check decorator
    """
    async def predicate(ctx):
        return has_mod_permissions(ctx.author, ctx.bot, required_discord_perm)
    
    return commands.check(predicate)
