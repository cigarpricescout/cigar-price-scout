#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv
from cj_famous_integration import CJFamousSmokeIntegrator

# Load environment variables from project root
project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(project_root / '.env')

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
