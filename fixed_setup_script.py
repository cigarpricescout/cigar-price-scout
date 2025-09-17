#!/usr/bin/env python3
"""
Setup script for CJ API integration with Famous Smoke Shop
"""

import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file with CJ API configuration"""
    env_content = """# CJ Affiliate API Configuration for Cigar Price Scout
# Your specific CJ Affiliate credentials:

# Get your Personal Access Token from https://developers.cj.com/
# 1. Log into CJ Developer Portal with your CJ credentials
# 2. Go to Authentication > Personal Access Tokens
# 3. Create a new token and copy it here
CJ_PERSONAL_ACCESS_TOKEN=your_personal_access_token_here

# Your specific CJ account details (already filled in):
CJ_WEBSITE_ID=101532120  # Your Publisher ID
CJ_COMPANY_ID=7711335    # Your Company ID

# Optional: Set to 'true' to enable debug logging
CJ_DEBUG=false
"""
    
    env_file = Path('.env')
    if not env_file.exists():
        with open(env_file, 'w') as f:
            f.write(env_content)
        print("OK Created .env file - please update with your CJ credentials")
    else:
        print("OK .env file already exists")

def create_backup_directory():
    """Create backup directory for CSV files"""
    backup_dir = Path('backups')
    backup_dir.mkdir(exist_ok=True)
    print("OK Created backups directory")

def install_required_packages():
    """Install required Python packages"""
    packages = ['requests', 'python-dotenv']
    
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"OK {package} already installed")
        except ImportError:
            print(f"Installing {package}...")
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            print(f"OK Installed {package}")

def create_cj_test_script():
    """Create a test script to verify CJ API connection"""
    test_script = """#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from cj_famous_integration import CJFamousSmokeIntegrator

# Load environment variables
load_dotenv()

def test_cj_connection():
    personal_access_token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
    
    if not personal_access_token or personal_access_token == 'your_personal_access_token_here':
        print("