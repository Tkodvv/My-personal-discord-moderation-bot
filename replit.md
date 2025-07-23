# Discord Moderation Bot

## Overview

This is a Discord moderation bot built with Python using the discord.py library. The bot provides moderation and utility commands through Discord's slash command system, with proper permission checking and role hierarchy validation.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Architecture Pattern
- **Cog-based Architecture**: The bot uses Discord.py's cog system to organize commands into logical modules
- **Slash Commands**: Primary interface using Discord's modern slash command system with fallback prefix commands
- **Event-driven**: Built on Discord.py's async event loop architecture

### Main Components
- `main.py`: Entry point with error handling and environment setup
- `bot.py`: Core bot class with event handlers and cog management
- `cogs/`: Modular command organization
- `utils/`: Shared utilities and helper functions

## Key Components

### Bot Core (`bot.py`)
- **DiscordBot Class**: Extends `commands.Bot` with slash command support
- **Intent Configuration**: Enables message content, members, guilds, and moderation intents
- **Cog Loading**: Automatically loads moderation and utility cogs during setup
- **Command Syncing**: Syncs slash commands with Discord API on startup

### Command Modules (Cogs)

#### Moderation Cog (`cogs/moderation.py`)
- **Purpose**: Handles server moderation actions
- **Commands**: kick, ban, timeout, untimeout, unban
- **Features**: Permission checking, role hierarchy validation, action logging

#### Utility Cog (`cogs/utility.py`)
- **Purpose**: Provides informational and utility commands
- **Commands**: userinfo, avatar, serverinfo, ping, roleinfo, uptime
- **Features**: Rich embed formatting, optional parameters, uptime tracking

#### Admin Cog (`cogs/admin.py`)
- **Purpose**: Administrative commands for server management
- **Commands**: say, announce, clear, snipe, setprefix
- **Features**: Message management, announcements, deleted message tracking

### Utility Systems

#### Logging (`utils/logging_config.py`)
- **Multi-handler Setup**: Console, error file, and general file logging
- **Structured Formatting**: Timestamped logs with level and module information
- **Library Filtering**: Reduces verbosity from Discord.py and urllib3

#### Permissions (`utils/permissions.py`)
- **Role Hierarchy**: Validates moderator can act on target based on role position
- **Permission Checking**: Verifies required Discord permissions
- **Safety Checks**: Prevents self-moderation and owner targeting

## Data Flow

1. **Bot Startup**: Load environment variables → Initialize bot → Load cogs → Sync commands
2. **Command Execution**: User invokes slash command → Permission validation → Action execution → Response/logging
3. **Error Handling**: Exceptions caught at multiple levels with appropriate user feedback

## External Dependencies

### Required Libraries
- `discord.py`: Core Discord API interaction
- `python-dotenv`: Environment variable management
- `asyncio`: Async runtime (built-in)

### Environment Variables
- `DISCORD_TOKEN`: Bot authentication token (required)

### Discord API Integration
- **Slash Commands**: Modern Discord command interface
- **Embeds**: Rich message formatting
- **Permissions**: Discord's permission system integration
- **Intents**: Specific data access permissions

## Deployment Strategy

### Local Development
- Environment variables loaded from `.env` file
- Console and file logging for debugging
- Hot-reload capability through cog system

### Production Considerations
- Token security through environment variables
- Error logging to files for monitoring
- Graceful shutdown handling
- No database requirements (stateless design)

### Dependencies Installation
```bash
pip install discord.py python-dotenv
```

### Configuration Requirements
1. Create Discord application and bot
2. Set `DISCORD_TOKEN` in `.env` file (template provided)
3. Configure bot permissions in Discord Developer Portal
4. Invite bot to server with appropriate permissions

### Windows Support
- `start.bat` script for easy Windows deployment
- Automatic dependency installation
- Error checking and user-friendly messages
- `.env` file validation

## Notes for Development

- Bot uses modern Discord features (slash commands, intents)
- Modular design allows easy addition of new command categories
- Permission system prevents privilege escalation
- Comprehensive logging aids in debugging and monitoring
- No persistent data storage - all state is ephemeral