# Keep-Alive Test Script
# This script demonstrates the keep-alive functionality without running the full bot

import asyncio
import logging
from datetime import datetime
from discord.ext import tasks

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KeepAliveTest:
    def __init__(self):
        self.boot_time = datetime.utcnow()
        self._keep_alive_counter = 0
        
    @tasks.loop(seconds=10)  # Fast interval for testing (10 seconds instead of 5 minutes)
    async def keep_alive_task(self):
        """Keep-alive task to prevent VS Code from timing out the bot."""
        try:
            logger.info(f"Keep-alive ping #{self._keep_alive_counter + 1}")
            
            self._keep_alive_counter += 1
            if self._keep_alive_counter >= 3:  # Show heartbeat every 3 pings for testing
                logger.info(f"Bot keep-alive heartbeat - Uptime: {self._get_uptime_string()}")
                self._keep_alive_counter = 0
                
        except Exception as e:
            logger.warning(f"Keep-alive task error: {e}")

    @keep_alive_task.before_loop
    async def before_keep_alive_task(self):
        """Wait before starting the keep-alive task."""
        logger.info("Keep-alive task starting...")
        await asyncio.sleep(1)  # Small delay to simulate bot startup

    def _get_uptime_string(self) -> str:
        """Get a formatted uptime string."""
        delta = datetime.utcnow() - self.boot_time
        minutes, seconds = divmod(delta.seconds, 60)
        return f"{minutes}m {seconds}s"

async def test_keep_alive():
    """Test the keep-alive functionality."""
    tester = KeepAliveTest()
    
    try:
        logger.info("Starting keep-alive test...")
        tester.keep_alive_task.start()
        
        # Run for 35 seconds to see multiple pings and a heartbeat
        await asyncio.sleep(35)
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        tester.keep_alive_task.cancel()
        logger.info("Keep-alive test completed")

if __name__ == "__main__":
    print("Keep-Alive Functionality Test")
    print("This test will run for 35 seconds showing periodic pings")
    print("Press Ctrl+C to stop early")
    print("-" * 50)
    
    asyncio.run(test_keep_alive())
