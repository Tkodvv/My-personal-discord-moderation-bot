@echo off
title Discord Moderation Bot
echo Starting Discord Moderation Bot...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found!
    echo Please create a .env file with your DISCORD_TOKEN
    echo Example:
    echo DISCORD_TOKEN=your_discord_bot_token_here
    echo.
    pause
    exit /b 1
)

REM Install required packages
echo Installing required packages...
pip install discord.py python-dotenv

REM Check if installation was successful
if errorlevel 1 (
    echo ERROR: Failed to install required packages
    pause
    exit /b 1
)

echo.
echo Starting bot...
echo Press Ctrl+C to stop the bot
echo.

REM Run the bot
python main.py

REM Pause if there was an error
if errorlevel 1 (
    echo.
    echo Bot stopped with an error. Check the logs above.
    pause
)