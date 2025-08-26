#!/usr/bin/env python3.12
"""
Discord Moderation Bot Entry Point for KataBump
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main function
from main import main

if __name__ == "__main__":
    main()
