#!/usr/bin/env python3
"""
Railway Deployment Preparation Script
Prepares your cigar price automation system for Railway deployment
"""

import os
import shutil
import zipfile
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
    
    # Core automation files
    core_files = [
        "automation_master.py",
        "requirements.txt", 
        "Dockerfile",
        "railway.json",
        "railway.env.template"
    ]
    
    # Copy core files
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
    
    # Copy extractors (you'll need to provide these)
    print("\n[EXTRACTORS] Files needed in tools/price_monitoring/retailers/:")
    for file in extractor_files:
        print(f"[NEED] {file}")
    
    # Create app directory for updater scripts
    app_dir = deploy_dir / "app"  
    app_dir.mkdir()
    
    updater_files = [
        "update_atlantic_prices_final.py",
        "update_foxcigar_prices_final.py",
        "update_nicks_prices_final.py"  # You'll create this
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
    
    print("\n[NEXT STEPS]:")
    print("1. Copy your extractor files to railway_deployment/tools/price_monitoring/retailers/")
    print("2. Copy your updater scripts to railway_deployment/app/")  
    print("3. Copy your actual CSV files to railway_deployment/static/data/")
    print("4. Copy your master_cigars.csv to railway_deployment/data/")
    print("5. Upload to Railway and configure environment variables")
    
    print(f"\n[COMPLETE] All files prepared in: {deploy_dir.absolute()}")

if __name__ == "__main__":
    prepare_railway_deployment()
# Cigar Price Scout - Railway Deployment

## Setup Instructions

1. **Create Railway Project**
   ```bash
   railway login
   railway init
   ```

2. **Set Environment Variables in Railway Dashboard:**
   - Copy variables from `railway.env.template`
   - Configure email settings (optional)
   - Set MASTER_CIGARS_URL if using Google Sheets

3. **Upload Your Files:**
   - Copy your extractor files to `retailers/` directory
   - Copy your updater scripts to `updaters/` directory  
   - Upload your actual CSV files to `static/data/`

4. **Deploy:**
   ```bash
   railway up
   ```

## Manual Testing Commands

```bash
# Test single retailer
python automation_master.py manual atlantic

# Test all retailers
python automation_master.py manual

# Test mode (Atlantic only)
python automation_master.py test
```

## Monitoring

- Check Railway logs for automation status
- Email notifications (if configured) for update results
- Weekly automated updates on Sundays at 3 AM UTC

## File Structure Required

```
/app
├── automation_master.py           # Main orchestrator
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container configuration
├── retailers/                     # Extractor modules
│   ├── __init__.py
│   ├── fox_cigar.py
│   ├── atlantic_cigar.py
│   └── nicks_cigars.py
├── updaters/                      # Update scripts
│   ├── update_atlantic_prices_final.py
│   ├── update_foxcigar_prices_final.py
│   └── update_nicks_prices_final.py
├── data/                          # Master data files
│   └── master_cigars.csv
├── static/data/                   # Retailer CSV files
│   ├── atlantic.csv
│   ├── foxcigar.csv
│   └── nickscigarworld.csv
└── logs/                          # Log files
    └── automation.log
```
"""
    
    (deploy_dir / "README.md").write_text(readme_content)
    print(f"✅ Created deployment README")
    
    # Create zip file for easy upload
    zip_path = "cigar_price_scout_railway.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file_path in deploy_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(deploy_dir)
                zipf.write(file_path, arcname)
    
    print(f"✅ Created deployment package: {zip_path}")
    
    print("\n🎯 NEXT STEPS:")
    print("1. Copy your extractor files (fox_cigar.py, etc.) to railway_deployment/retailers/")
    print("2. Copy your updater scripts to railway_deployment/updaters/")  
    print("3. Copy your CSV files to railway_deployment/static/data/")
    print("4. Upload to Railway and configure environment variables")
    print("5. Deploy and test!")
    
    print(f"\n📦 All files prepared in: {deploy_dir.absolute()}")
    print(f"📁 Deployment package: {Path(zip_path).absolute()}")

if __name__ == "__main__":
    prepare_railway_deployment()
