# Discord Moderation Bot

A comprehensive Discord moderation bot built with Python and discord.py v2.3+, featuring modern slash commands and extensive moderation capabilities.

## Features

### 🛡️ Moderation Commands
- `/kick` - Remove members from the server
- `/ban` - Ban members with optional message deletion
- `/timeout` - Temporarily restrict member access (up to 28 days)
- `/untimeout` - Remove timeout from members
- `/unban` - Restore access to banned users

### 📊 Utility Commands
- `/userinfo` - Detailed member information and statistics
- `/avatar` - High-resolution avatar display with download links
- `/serverinfo` - Complete server information and statistics
- `/roleinfo` - Detailed role information and permissions
- `/ping` - Check bot latency and response time
- `/uptime` - Show how long the bot has been running

### ⚙️ Administrative Commands
- `/say` - Make the bot send custom messages
- `/announce` - Send formatted announcement embeds
- `/clear` - Delete messages with optional user filtering
- `/snipe` - View recently deleted messages
- `/setprefix` - Change the bot's command prefix

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- A Discord bot token

### Getting Your Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section in the left sidebar
4. Click "Add Bot" if needed
5. Under "Token", click "Copy" to get your bot token
6. Enable these "Privileged Gateway Intents":
   - Server Members Intent
   - Message Content Intent

### Installation

#### Windows (Easy Setup)
1. Download all bot files to a folder
2. Edit the `.env` file and replace `your_discord_bot_token_here` with your actual bot token
3. Double-click `start.bat` to run the bot

#### Manual Installation (All Platforms)
1. Clone or download the bot files
2. Install dependencies:
   ```bash
   pip install discord.py python-dotenv
   ```
3. Create/edit the `.env` file:
   ```
   DISCORD_TOKEN=your_actual_bot_token_here
   ```
4. Run the bot:
   ```bash
   python main.py
   ```

### Bot Permissions
When inviting your bot to a server, make sure it has these permissions:
- Send Messages
- Use Slash Commands
- Embed Links
- Read Message History
- Kick Members
- Ban Members
- Moderate Members (for timeouts)
- Manage Messages (for clear command)

## Project Structure

```
├── cogs/
│   ├── moderation.py    # Moderation commands
│   ├── utility.py       # Information commands
│   └── admin.py         # Administrative commands
├── utils/
│   ├── logging_config.py # Logging configuration
│   └── permissions.py    # Permission utilities
├── main.py              # Bot entry point
├── bot.py               # Core bot class
├── start.bat            # Windows startup script
├── .env                 # Configuration file
└── .env.example         # Configuration template
```

## Security Features

- **Role Hierarchy Validation**: Prevents privilege escalation
- **Permission Checking**: Comprehensive permission validation
- **Error Handling**: Graceful handling of missing permissions
- **Audit Logging**: All moderation actions are logged

## Customization

The bot uses a modular cog system, making it easy to:
- Add new commands
- Modify existing functionality
- Disable specific features
- Customize permission requirements

## Support

If you encounter issues:
1. Check that your bot token is correct in the `.env` file
2. Verify the bot has necessary permissions in your Discord server
3. Check the console output for error messages
4. Ensure all dependencies are installed correctly

## License

This project is open source and available under the MIT License.