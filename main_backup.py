#!/usr/bin/env python3
"""
Render Test - Web Server Only
This version starts ONLY the web server to test Render deployment
"""

import os
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks."""
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Slice Moderation Bot</title></head>
        <body>
            <h1>🤖 Discord Bot is Running!</h1>
            <p>✅ Web server is working correctly</p>
            <p>🚀 Ready for Discord bot deployment</p>
        </body>
        </html>
        """
        self.wfile.write(html_content.encode())
    
    def do_POST(self):
        self.do_GET()
    
    def log_message(self, format, *args):
        # Log HTTP requests
        logger.info(f"HTTP Request: {format % args}")


def main():
    """Main function - starts web server only for testing."""
    try:
        # Get port from environment
        port = int(os.environ.get('PORT', 8080))
        
        logger.info("=" * 50)
        logger.info("🚀 STARTING RENDER TEST SERVER")
        logger.info("=" * 50)
        logger.info(f"📡 PORT environment: {os.environ.get('PORT', 'NOT SET')}")
        logger.info(f"🌐 Binding to: 0.0.0.0:{port}")
        
        # Create and start server
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        
        logger.info("✅ Server bound successfully!")
        logger.info(f"🌍 Server URL: http://0.0.0.0:{port}")
        logger.info("🔄 Starting server loop...")
        logger.info("=" * 50)
        
        # Start the server
        server.serve_forever()
        
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}")
        logger.error(f"❌ Failed to start server on port {port}")
        
        # Keep process alive even if server fails
        logger.info("🔄 Keeping process alive...")
        while True:
            time.sleep(60)
            logger.info("💓 Process still running...")


if __name__ == "__main__":
    main()
