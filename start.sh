#!/bin/bash

# Katabump deployment script
echo "Starting Discord Moderation Bot deployment..."

# Install Python dependencies
pip install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p data

# Set permissions
chmod +x main.py

echo "Dependencies installed successfully!"
echo "Starting bot..."

# Run the bot
python main.py
