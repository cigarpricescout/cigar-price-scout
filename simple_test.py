#!/usr/bin/env python3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Simple test to check if our class works
try:
    from cj_famous_integration import CJFamousSmokeIntegrator
    print("Successfully imported CJFamousSmokeIntegrator")
    
    personal_access_token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
    print(f"Token found: {personal_access_token is not None}")
    
    # Try to create the integrator
    integrator = CJFamousSmokeIntegrator(
        personal_access_token=personal_access_token,
        website_id="101532120", 
        cid="7711335"
    )
    print("SUCCESS: CJFamousSmokeIntegrator created successfully!")
    
except Exception as e:
    print(f"ERROR: {e}")
    print("Please check that cj_famous_integration.py is created correctly")