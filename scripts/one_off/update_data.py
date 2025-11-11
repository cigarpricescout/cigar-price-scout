#!/usr/bin/env python3
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
