from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess
import logging

logger = logging.getLogger(__name__)

def run_feed_processor():
    """Run the CJ feed processing script"""
    try:
        result = subprocess.run(
            ['python', 'scripts/process_cj_feeds.py'],
            capture_output=True,
            text=True
        )
        logger.info(f"Feed processor completed: {result.stdout}")
        if result.stderr:
            logger.error(f"Feed processor errors: {result.stderr}")
    except Exception as e:
        logger.error(f"Failed to run feed processor: {e}")

def start_scheduler():
    """Start the background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Run daily at 3 AM Pacific
    scheduler.add_job(
        run_feed_processor,
        CronTrigger(hour=3, minute=0, timezone='America/Los_Angeles'),
        id='cj_feed_processor',
        name='Process CJ affiliate feeds',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started - CJ feeds will process daily at 3 AM Pacific")