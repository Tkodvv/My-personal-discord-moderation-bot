#!/bin/bash

# Katabump deployment script for Discord Bot
echo "🚀 Starting Discord Moderation Bot deployment..."

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found in current directory"
    echo "📁 Current directory contents:"
    ls -la
    exit 1
fi

# Install Python dependencies
echo "📦 Installing dependencies..."
pip3.12 install -r requirements.txt || pip3 install -r requirements.txt || pip install -r requirements.txt

# Create data directory if it doesn't exist
echo "📂 Setting up data directory..."
mkdir -p data

# Set permissions
chmod +x main.py

echo "✅ Dependencies installed successfully!"
echo "🤖 Starting Discord bot..."

# Try different Python commands
if command -v python3.12 &> /dev/null; then
    echo "Using python3.12..."
    python3.12 main.py
elif command -v python3 &> /dev/null; then
    echo "Using python3..."
    python3 main.py
else
    echo "Using python..."
    python main.py
fi
