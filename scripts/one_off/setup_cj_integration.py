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
        print("ERROR: Please set CJ_PERSONAL_ACCESS_TOKEN in your .env file")
        print("   Get it from: https://developers.cj.com/ > Authentication > Personal Access Tokens")
        return False
    
    print("Testing CJ API connection...")
    print(f"Using Website ID: 101532120")
    print(f"Using Company ID: 7711335")
    
    integrator = CJFamousSmokeIntegrator(
        personal_access_token=personal_access_token,
        website_id="101532120",
        cid="7711335"
    )
    
    # Test basic API connectivity
    print("Discovering Famous Smoke Shop advertiser ID...")
    advertiser_id = integrator.discover_famous_advertiser_id()
    
    if advertiser_id:
        print(f"SUCCESS: Successfully connected to CJ API!")
        print(f"   Famous Smoke Shop Advertiser ID: {advertiser_id}")
        return True
    else:
        print("ERROR: Could not connect to CJ API or find Famous Smoke Shop")
        print("   Possible issues:")
        print("   1. Check your Personal Access Token")
        print("   2. Ensure you're approved for Famous Smoke Shop affiliate program")
        print("   3. Verify Famous Smoke Shop has products in CJ's product feed")
        return False

if __name__ == "__main__":
    test_cj_connection()
"""
    
    with open('test_cj_connection.py', 'w') as f:
        f.write(test_script)
    print("OK Created test_cj_connection.py")

def create_update_script():
    """Create a simple update script for regular use"""
    update_script = """#!/usr/bin/env python3
from dotenv import load_dotenv
from enhanced_batch_updates import EnhancedBatchUpdater
import os

# Load environment variables
load_dotenv()

def main():
    print("Starting Cigar Price Scout data update...")
    
    # Get Personal Access Token from environment
    personal_access_token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
    
    # Your specific CJ credentials (pre-configured)
    website_id = "101532120"  # Your Publisher ID
    cid = "7711335"           # Your Company ID
    
    # Create and run updater
    updater = EnhancedBatchUpdater(personal_access_token, website_id, cid)
    updater.run_full_update()
    
    print("Update complete!")

if __name__ == "__main__":
    main()
"""
    
    with open('update_data.py', 'w') as f:
        f.write(update_script)
    
    # Make it executable on Unix systems
    if os.name != 'nt':
        os.chmod('update_data.py', 0o755)
    
    print("OK Created update_data.py")

def show_next_steps():
    """Show user what to do next"""
    print("\n" + "="*60)
    print("NEXT STEPS TO COMPLETE SETUP:")
    print("="*60)
    print()
    print("1. UPDATE YOUR .env FILE:")
    print("   • Edit the .env file created in this directory")
    print("   • Replace 'your_personal_access_token_here' with: s64Z7FGpWmmCDbdHlfcweg-MZA")
    print()
    print("2. TEST THE CONNECTION:")
    print("   • Run: python test_cj_connection.py")
    print("   • This will verify your API credentials work")
    print()
    print("3. RUN YOUR FIRST UPDATE:")
    print("   • Run: python update_data.py")
    print("   • This will update your Famous Smoke data via CJ API")
    print()
    print("FILES CREATED:")
    print("   • .env - Your API configuration")
    print("   • test_cj_connection.py - Connection test script")
    print("   • update_data.py - Simple update runner")
    print("   • backups/ - Directory for CSV backups")
    print()
    print("IMPORTANT NOTES:")
    print("   • Your CJ credentials are already configured in the scripts")
    print("   • Website ID: 101532120")
    print("   • Company ID: 7711335")
    print("   • Just add your Personal Access Token to the .env file")

def verify_project_structure():
    """Verify the project has the expected structure"""
    required_dirs = ['static/data', 'app']
    required_files = ['app/main.py', 'static/index.html']
    
    print("\nVERIFYING PROJECT STRUCTURE:")
    print("-" * 40)
    
    all_good = True
    
    for directory in required_dirs:
        if os.path.exists(directory):
            print(f"OK {directory}/ exists")
        else:
            print(f"MISSING {directory}/")
            all_good = False
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"OK {file_path} exists")
        else:
            print(f"MISSING {file_path}")
            all_good = False
    
    if all_good:
        print("Project structure looks good!")
    else:
        print("Some expected files/directories are missing")
        print("   Make sure you're running this in your cigar-price-scout directory")
    
    return all_good

def main():
    """Main setup function"""
    print("SETTING UP CJ API INTEGRATION FOR CIGAR PRICE SCOUT")
    print("=" * 60)
    
    # Verify we're in the right directory
    if not verify_project_structure():
        print("\nSetup cancelled - please run from your project root directory")
        return
    
    print("\nINSTALLING REQUIREMENTS...")
    install_required_packages()
    
    print("\nCREATING DIRECTORIES...")
    create_backup_directory()
    
    print("\nCREATING CONFIGURATION FILES...")
    create_env_file()
    create_cj_test_script()
    create_update_script()
    
    print("\nSETUP COMPLETE!")
    show_next_steps()

if __name__ == "__main__":
    main()