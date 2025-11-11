#!/usr/bin/env python3
"""
Copy all necessary files to railway_deployment folder
"""

import shutil
from pathlib import Path

def copy_files_to_deployment():
    deploy_dir = Path("railway_deployment")
    
    # Copy the core automation files we created
    files_to_copy = {
        "../tools/price_monitoring/retailers/fox_cigar.py": "tools/price_monitoring/retailers/fox_cigar.py",
        "../tools/price_monitoring/retailers/atlantic_cigar_extractor.py": "tools/price_monitoring/retailers/atlantic_cigar_extractor.py", 
        "../tools/price_monitoring/retailers/nicks_cigars.py": "tools/price_monitoring/retailers/nicks_cigars.py",
        "update_atlantic_prices_final.py": "app/update_atlantic_prices_final.py",
        "update_foxcigar_prices_final.py": "app/update_foxcigar_prices_final.py",
        "../static/data/atlantic.csv": "static/data/atlantic.csv",
        "../static/data/foxcigar.csv": "static/data/foxcigar.csv",
        "../data/master_cigars.csv": "data/master_cigars.csv"
    }
    
    print("COPYING FILES TO RAILWAY DEPLOYMENT")
    print("=" * 40)
    
    for source, dest in files_to_copy.items():
        source_path = Path(source)
        dest_path = deploy_dir / dest
        
        if source_path.exists():
            # Create parent directories if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            print(f"[OK] Copied {source} -> {dest}")
        else:
            print(f"[MISSING] {source}")
    
    # Create requirements.txt
    requirements = """requests>=2.31.0
beautifulsoup4>=4.12.2
pandas>=2.0.3
lxml>=4.9.3
schedule>=1.2.0
python-dotenv>=1.0.0
APScheduler>=3.10.4
"""
    (deploy_dir / "requirements.txt").write_text(requirements)
    print("[OK] Created requirements.txt")
    
    # Create Dockerfile
    dockerfile = """FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p data static/data logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Make automation script executable
RUN chmod +x automation_master.py

# Command to run the automation
CMD ["python", "automation_master.py"]
"""
    (deploy_dir / "Dockerfile").write_text(dockerfile)
    print("[OK] Created Dockerfile")
    
    # Create railway.json
    railway_json = """{
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}"""
    (deploy_dir / "railway.json").write_text(railway_json)
    print("[OK] Created railway.json")
    
    # Create environment template
    env_template = """# Cigar Price Scout - Railway Environment Variables

# Email Notifications (Optional - leave blank to disable)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=your-notifications@email.com

# Railway Configuration
PORT=8000

# Automation Settings
UPDATE_SCHEDULE_CRON=0 3 * * SUN
MAX_UPDATE_DURATION_MINUTES=30

# Logging Level
LOG_LEVEL=INFO
"""
    (deploy_dir / "railway.env.template").write_text(env_template)
    print("[OK] Created railway.env.template")
    
    print("\n[SUCCESS] Deployment package ready!")
    print(f"Location: {deploy_dir.absolute()}")
    print("\n[NEXT STEPS]:")
    print("1. Check that all your files were copied correctly")
    print("2. Create a Railway account at railway.app")
    print("3. Deploy using Railway CLI or GitHub integration")
    print("4. Configure environment variables from the template")

if __name__ == "__main__":
    copy_files_to_deployment()
