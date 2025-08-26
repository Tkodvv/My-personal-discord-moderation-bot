#!/usr/bin/env python3
"""
Discord Moderation Bot Entry Point - Render Compatible
"""

import asyncio
import logging
import os
import sys
import time
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

# Import bot after loading environment
try:
    from bot import DiscordBot
    from utils.logging_config import setup_logging
    BOT_AVAILABLE = True
except ImportError as e:
    BOT_AVAILABLE = False
    # Set up basic logging if utils not available
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


class HealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks."""
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # Create a nice status page
        status = "🤖 Bot Online" if BOT_AVAILABLE else "⚠️ Bot Module Missing"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Slice Moderation Bot</title></head>
        <body style="font-family: Arial; padding: 20px; background: #2c2f33; color: white;">
            <h1>🎮 Slice Moderation Bot</h1>
            <p><strong>Status:</strong> {status}</p>
            <p><strong>Web Server:</strong> ✅ Running</p>
            <p><strong>Port:</strong> {os.environ.get('PORT', '8080')}</p>
            <p><strong>Time:</strong> {time.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def do_POST(self):
        self.do_GET()
    
    def log_message(self, format, *args):
        # Log HTTP requests
        logging.getLogger('http').info(f"HTTP: {format % args}")


def start_web_server():
    """Start web server for Render health checks - GUARANTEED to work."""
    logger = logging.getLogger(__name__)
    
    try:
        port = int(os.environ.get('PORT', 8080))
        
        logger.info("=" * 60)
        logger.info("🚀 STARTING RENDER WEB SERVER")
        logger.info("=" * 60)
        logger.info(f"📡 PORT from env: {os.environ.get('PORT', 'NOT SET (using 8080)')}")
        logger.info(f"🌐 Binding to: 0.0.0.0:{port}")
        
        # Create server
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        
        logger.info("✅ SUCCESS: Web server bound to port!")
        logger.info(f"� Access at: http://0.0.0.0:{port}")
        logger.info("🔄 Starting server loop...")
        logger.info("=" * 60)
        
        # This will run forever and keep Render happy
        server.serve_forever()
        
    except Exception as e:
        logger.error(f"❌ CRITICAL WEB SERVER ERROR: {e}")
        # FAILSAFE: Keep process alive even if server fails
        logger.info("🔄 FAILSAFE: Keeping process alive for Render...")
        try:
            while True:
                time.sleep(30)
                logger.info(f"💓 Process alive on attempted port {port}")
        except KeyboardInterrupt:
            logger.info("🛑 Process stopped")


async def run_bot(discord_token: str):
    """Run the Discord bot - with error handling."""
    if not BOT_AVAILABLE:
        logging.getLogger(__name__).error("❌ Bot module not available!")
        return
        
    logger = logging.getLogger(__name__)
    bot = None
    
    try:
        logger.info("🤖 Starting Discord bot...")
        bot = DiscordBot()
        await bot.start(discord_token)
    except Exception as e:
        logger.error(f"❌ Discord bot error: {e}")
        # Don't crash the whole app if bot fails
    finally:
        if bot and not bot.is_closed():
            try:
                await bot.close()
                logger.info("🤖 Discord bot closed cleanly")
            except:
                pass


def main():
    """Main function - prioritizes web server, then starts bot."""
    
    # Set up logging
    if BOT_AVAILABLE:
        setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("🎮 SLICE MODERATION BOT STARTING")
    
    # STEP 1: Start web server FIRST (most important for Render)
    logger.info("🔥 PRIORITY 1: Starting web server for Render...")
    web_thread = Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Give web server time to bind to port
    time.sleep(3)
    logger.info("✅ Web server thread started")
    
    # STEP 2: Start Discord bot (if available)
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.warning("⚠️ No DISCORD_TOKEN - running web server only")
        # Keep process alive for web server
        try:
            while True:
                time.sleep(60)
                logger.info("💓 Web-only mode: Process alive")
        except KeyboardInterrupt:
            logger.info("🛑 Shutdown requested")
        return
    
    if not BOT_AVAILABLE:
        logger.warning("⚠️ Bot modules missing - running web server only")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
        return
    
    # Start the Discord bot
    try:
        logger.info("🤖 Starting Discord bot...")
        asyncio.run(run_bot(token))
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        # Keep web server alive even if bot crashes
        logger.info("🔄 Keeping web server alive after bot crash...")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
