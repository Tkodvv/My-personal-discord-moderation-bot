#!/usr/bin/env python3
"""
Discord Moderation Bot Entry Point - Flask Version
"""

import asyncio
import logging
import os
import sys
from threading import Thread
from dotenv import load_dotenv

from bot import DiscordBot
from utils.logging_config import setup_logging

# Flask-based web server (more reliable for deployment)
try:
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    def health_check():
        return 'Discord Bot is running!', 200
    
    @app.route('/health')
    def health():
        return {'status': 'healthy'}, 200
        
    def start_web_server():
        """Start Flask web server for Render health checks."""
        try:
            port = int(os.environ.get('PORT', 8080))
            logger = logging.getLogger(__name__)
            logger.info(f"Starting Flask web server on 0.0.0.0:{port}")
            
            # Disable Flask's default logging to reduce noise
            import logging as flask_logging
            flask_logging.getLogger('werkzeug').setLevel(flask_logging.WARNING)
            
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to start Flask server: {e}")
            raise
            
except ImportError:
    # Fallback to http.server if Flask not available
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Discord Bot is running!')
        
        def log_message(self, format, *args):
            pass
    
    def start_web_server():
        """Start basic HTTP server for Render health checks."""
        try:
            port = int(os.environ.get('PORT', 8080))
            logger = logging.getLogger(__name__)
            logger.info(f"Starting HTTP server on 0.0.0.0:{port}")
            
            server = HTTPServer(('0.0.0.0', port), HealthHandler)
            logger.info(f"Server bound successfully to port {port}")
            server.serve_forever()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to start HTTP server: {e}")
            raise

load_dotenv()


async def run_bot(discord_token: str):
    bot = DiscordBot()
    try:
        await bot.start(discord_token)
    except asyncio.CancelledError:
        pass
    finally:
        if not bot.is_closed():
            await bot.close()


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN environment variable not found!")
        sys.exit(1)

    # Start web server in background thread for Render
    try:
        web_thread = Thread(target=start_web_server)
        web_thread.daemon = True
        web_thread.start()
        logger.info("Web server thread started successfully")
        
        # Give the web server time to start
        import time
        time.sleep(3)
        
    except Exception as e:
        logger.error(f"Failed to start web server thread: {e}")

    try:
        logger.info("Starting Discord Moderation Bot...")
        asyncio.run(run_bot(token))
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except asyncio.CancelledError:
        logger.info("Bot task was cancelled")
    except Exception as e:
        logger.error("Fatal error occurred: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
