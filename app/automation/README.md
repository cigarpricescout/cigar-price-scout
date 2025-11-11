# Cigar Price Scout - Railway Deployment

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
