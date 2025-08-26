#!/usr/bin/env python3
"""
Test the web server component separately
"""
import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Web server test - OK!')
    
    def log_message(self, format, *args):
        logger.info(format % args)

def test_web_server():
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Testing web server on port {port}")
    
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"Server bound successfully to 0.0.0.0:{port}")
        logger.info("Server starting... Press Ctrl+C to stop")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Server failed: {e}")

if __name__ == "__main__":
    test_web_server()
