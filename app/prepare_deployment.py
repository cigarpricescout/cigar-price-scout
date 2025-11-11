#!/usr/bin/env python3
"""
Railway Deployment Preparation Script
Prepares your cigar price automation system for Railway deployment
"""

import os
import shutil
from pathlib import Path

def prepare_railway_deployment():
    """Prepare all files for Railway deployment"""
    
    print("PREPARING CIGAR PRICE SCOUT FOR RAILWAY DEPLOYMENT")
    print("=" * 60)
    
    # Create deployment directory
    deploy_dir = Path("railway_deployment")
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    deploy_dir.mkdir()
    
    print(f"[INFO] Created deployment directory: {deploy_dir}")
    
    # Core automation files needed
    core_files = [
        "automation_master.py",
        "requirements.txt", 
        "Dockerfile",
        "railway.json",
        "railway.env.template"
    ]
    
    # Copy core files if they exist
    for file in core_files:
        if Path(file).exists():
            shutil.copy2(file, deploy_dir / file)
            print(f"[OK] Copied {file}")
        else:
            print(f"[MISSING] {file} - you'll need this file")
    
    # Create tools directory structure (matching your existing structure)
    tools_dir = deploy_dir / "tools" / "price_monitoring"
    tools_dir.mkdir(parents=True)
    
    # Create retailers directory inside tools
    retailers_dir = tools_dir / "retailers"
    retailers_dir.mkdir()
    
    # Create empty __init__.py files for Python packages
    (tools_dir / "__init__.py").write_text("")
    (retailers_dir / "__init__.py").write_text("")
    
    # Extractor files to include (matching your existing structure)
    extractor_files = [
        "fox_cigar.py",
        "atlantic_cigar_extractor.py", 
        "nicks_cigars.py"
    ]
    
    # List extractors needed
    print("\n[EXTRACTORS] Files needed in tools/price_monitoring/retailers/:")
    for file in extractor_files:
        print(f"[NEED] {file}")
    
    # Create app directory for updater scripts
    app_dir = deploy_dir / "app"  
    app_dir.mkdir()
    
    updater_files = [
        "update_atlantic_prices_final.py",
        "update_foxcigar_prices_final.py",
        "update_nicks_prices_final.py"
    ]
    
    print("\n[UPDATERS] Files needed in app/:")
    for file in updater_files:
        print(f"[NEED] {file}")
    
    # Create data directories (matching your existing structure)
    (deploy_dir / "data").mkdir()  # For master_cigars.csv
    static_data_dir = deploy_dir / "static" / "data"
    static_data_dir.mkdir(parents=True)  # For retailer CSV files
    (deploy_dir / "logs").mkdir()
    
    print(f"[OK] Created data directories")
    
    # Create sample CSV files
    csv_files = ["atlantic.csv", "foxcigar.csv", "nickscigarworld.csv"]
    for csv_file in csv_files:
        sample_csv = static_data_dir / csv_file
        sample_csv.write_text("cigar_id,title,url,brand,line,wrapper,vitola,size,box_qty,price,in_stock\n")
        print(f"[OK] Created sample {csv_file}")
    
    # Create deployment README
    readme_content = """# Cigar Price Scout - Railway Deployment

## Setup Instructions

1. Create Railway Project:
   railway login
   railway init

2. Set Environment Variables in Railway Dashboard:
   - Copy variables from railway.env.template
   - Configure email settings (optional)

3. Upload Your Files:
   - Copy your extractor files to tools/price_monitoring/retailers/
   - Copy your updater scripts to app/
   - Upload your actual CSV files to static/data/
   - Upload master_cigars.csv to data/

4. Deploy:
   railway up

## Manual Testing Commands

# Test single retailer
python automation_master.py manual atlantic

# Test all retailers  
python automation_master.py manual

# Test mode (Atlantic only)
python automation_master.py test

## File Structure

/app
  automation_master.py           (Main orchestrator)
  requirements.txt               (Python dependencies)
  Dockerfile                     (Container configuration)
  tools/
    price_monitoring/
      retailers/
        fox_cigar.py
        atlantic_cigar_extractor.py
        nicks_cigars.py
  app/
    update_atlantic_prices_final.py
    update_foxcigar_prices_final.py
    update_nicks_prices_final.py
  data/
    master_cigars.csv
  static/data/
    atlantic.csv
    foxcigar.csv
    nickscigarworld.csv
  logs/
    automation.log
"""
    
    (deploy_dir / "README.md").write_text(readme_content)
    print(f"[OK] Created deployment README")
    
    print("\n[NEXT STEPS]:")
    print("1. Copy your extractor files to railway_deployment/tools/price_monitoring/retailers/")
    print("2. Copy your updater scripts to railway_deployment/app/")  
    print("3. Copy your actual CSV files to railway_deployment/static/data/")
    print("4. Copy your master_cigars.csv to railway_deployment/data/")
    print("5. Upload to Railway and configure environment variables")
    
    print(f"\n[COMPLETE] All files prepared in: {deploy_dir.absolute()}")

if __name__ == "__main__":
    prepare_railway_deployment()
