# Add these imports to your existing app/main.py
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import BackgroundTasks
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add this to your existing FastAPI app
class DataUpdateManager:
    """Manages automated data updates from various sources"""
    
    def __init__(self):
        self.last_update = {}
        self.update_intervals = {
            'famous': timedelta(hours=6),  # Update Famous Smoke every 6 hours
            'manual': timedelta(days=1)    # Process manual updates daily
        }
    
    def should_update(self, source: str) -> bool:
        """Check if a data source should be updated"""
        if source not in self.last_update:
            return True
        
        time_since_update = datetime.now() - self.last_update[source]
        return time_since_update >= self.update_intervals.get(source, timedelta(hours=24))
    
    def mark_updated(self, source: str):
        """Mark a data source as recently updated"""
        self.last_update[source] = datetime.now()
    
    async def update_famous_smoke(self):
        """Update Famous Smoke data via CJ API"""
        try:
            from enhanced_batch_updates import EnhancedBatchUpdater
            
            cj_key = os.getenv('CJ_DEVELOPER_KEY')
            website_id = os.getenv('CJ_WEBSITE_ID')
            
            if not cj_key or not website_id:
                print("CJ API credentials not configured")
                return False
            
            updater = EnhancedBatchUpdater(cj_key, website_id)
            
            # Run in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, updater.update_famous_via_api)
            
            self.mark_updated('famous')
            print(f"Updated Famous Smoke data at {datetime.now()}")
            return True
            
        except Exception as e:
            print(f"Error updating Famous Smoke data: {e}")
            return False

# Initialize the data manager
data_manager = DataUpdateManager()

# Add these new endpoints to your existing FastAPI app

@app.get("/admin/update-status")
async def get_update_status():
    """Get the status of data updates"""
    return {
        "last_updates": data_manager.last_update,
        "should_update": {
            source: data_manager.should_update(source) 
            for source in ['famous', 'manual']
        }
    }

@app.post("/admin/update-famous")
async def manual_update_famous(background_tasks: BackgroundTasks):
    """Manually trigger Famous Smoke data update"""
    background_tasks.add_task(data_manager.update_famous_smoke)
    return {"message": "Famous Smoke update started in background"}

@app.post("/admin/force-update-all")
async def force_update_all(background_tasks: BackgroundTasks):
    """Force update of all data sources"""
    background_tasks.add_task(data_manager.update_famous_smoke)
    
    # Also run manual updates
    try:
        from enhanced_batch_updates import EnhancedBatchUpdater
        updater = EnhancedBatchUpdater()
        background_tasks.add_task(updater.process_manual_updates)
    except Exception as e:
        print(f"Error setting up manual updates: {e}")
    
    return {"message": "Full data update started in background"}

# Add this background task to run periodic updates
@app.on_event("startup")
async def startup_tasks():
    """Tasks to run when the app starts"""
    print("Cigar Price Scout API starting up...")
    
    # Check if automatic updates should run
    if data_manager.should_update('famous'):
        print("Scheduling Famous Smoke data update...")
        asyncio.create_task(data_manager.update_famous_smoke())

# Modify your existing compare endpoint to include update status
@app.get("/compare")
async def compare_prices_enhanced(
    brand: str, 
    line: str, 
    wrapper: str, 
    vitola: str, 
    zip_code: str,
    auto_update: bool = False  # New parameter
):
    """
    Enhanced compare endpoint with optional auto-update
    """
    # Check if auto-update is requested and due
    if auto_update and data_manager.should_update('famous'):
        # Trigger background update
        asyncio.create_task(data_manager.update_famous_smoke())
    
    # Your existing compare logic here...
    # (keep all your existing code, just add the auto_update functionality)
    
    # Return your existing response with additional metadata
    response = await your_existing_compare_logic(brand, line, wrapper, vitola, zip_code)
    
    # Add update metadata to response
    response["update_status"] = {
        "last_famous_update": data_manager.last_update.get('famous'),
        "should_update_famous": data_manager.should_update('famous')
    }
    
    return response

# Add this helper function for CSV data freshness
def get_csv_file_age(filename: str) -> Optional[int]:
    """Get the age of a CSV file in hours"""
    filepath = f"static/data/{filename}"
    if os.path.exists(filepath):
        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        age = datetime.now() - file_time
        return int(age.total_seconds() / 3600)  # Return hours
    return None

@app.get("/admin/data-freshness")
async def get_data_freshness():
    """Get information about how fresh each retailer's data is"""
    data_dir = "static/data"
    freshness = {}
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.csv'):
                retailer = filename.replace('.csv', '')
                age_hours = get_csv_file_age(filename)
                freshness[retailer] = {
                    "age_hours": age_hours,
                    "status": "fresh" if age_hours and age_hours < 24 else "stale",
                    "last_modified": datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(data_dir, filename))
                    ).isoformat() if age_hours else None
                }
    
    return freshness

# Add configuration endpoint
@app.get("/admin/config")
async def get_config():
    """Get current configuration status"""
    return {
        "cj_api_configured": bool(os.getenv('CJ_PERSONAL_ACCESS_TOKEN')),
        "cj_website_id": "101532120",
        "cj_company_id": "7711335", 
        "famous_smoke_enabled": bool(os.path.exists('static/data/famous.csv')),
        "auto_update_intervals": {
            source: str(interval) for source, interval in data_manager.update_intervals.items()
        },
        "environment": os.getenv('ENVIRONMENT', 'development')
    }

# Optional: Add a simple admin dashboard endpoint
@app.get("/admin/dashboard")
async def admin_dashboard():
    """Simple admin dashboard data"""
    # Count products per retailer
    product_counts = {}
    data_dir = "static/data"
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.csv'):
                retailer = filename.replace('.csv', '')
                try:
                    import csv
                    with open(os.path.join(data_dir, filename), 'r') as f:
                        product_counts[retailer] = len(list(csv.DictReader(f)))
                except:
                    product_counts[retailer] = 0
    
    return {
        "total_retailers": len(product_counts),
        "total_products": sum(product_counts.values()),
        "products_per_retailer": product_counts,
        "system_status": "operational",
        "last_updates": data_manager.last_update
    }