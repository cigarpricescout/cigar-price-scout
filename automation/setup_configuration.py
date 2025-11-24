#!/usr/bin/env python3
"""
Configuration Setup for Automated Cigar Price System
Interactive script to configure email notifications and other settings
"""

import json
import getpass
from pathlib import Path

def setup_configuration():
    """Interactive configuration setup"""
    print("=" * 60)
    print("CIGAR PRICE SCOUT - AUTOMATION CONFIGURATION SETUP")
    print("=" * 60)
    print()
    
    config_file = Path('automation_config.json')
    
    # Load existing config if it exists
    if config_file.exists():
        print("Existing configuration found. Loading current settings...")
        with open(config_file, 'r') as f:
            config = json.load(f)
        print()
    else:
        print("Creating new configuration...")
        config = {
            "email_notifications": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "",
                "sender_password": "",
                "recipient_email": "",
                "send_on_success": True,
                "send_on_failure": True
            },
            "git_automation": {
                "enabled": True,
                "auto_commit": True,
                "auto_push": True,
                "commit_message_template": "Automated price update - {date}"
            },
            "price_update_settings": {
                "timeout_minutes": 30,
                "retry_failed_retailers": True,
                "delay_between_retailers": 2
            },
            "historical_tracking": {
                "enabled": True,
                "track_price_changes": True,
                "track_stock_changes": True,
                "retention_days": 365
            }
        }
        print()
    
    # Email notification setup
    print("EMAIL NOTIFICATION SETUP")
    print("-" * 30)
    print("Configure email notifications for automation results.")
    print()
    
    enable_email = input(f"Enable email notifications? [y/N]: ").lower().startswith('y')
    config["email_notifications"]["enabled"] = enable_email
    
    if enable_email:
        print("\nEmail Configuration:")
        print("(For Gmail, you'll need to use an App Password instead of your regular password)")
        print("Generate one at: https://myaccount.google.com/apppasswords")
        print()
        
        sender_email = input(f"Sender email [{config['email_notifications'].get('sender_email', '')}]: ").strip()
        if sender_email:
            config["email_notifications"]["sender_email"] = sender_email
        
        if config["email_notifications"]["sender_email"]:
            sender_password = getpass.getpass("Sender email password/app password: ")
            if sender_password:
                config["email_notifications"]["sender_password"] = sender_password
        
        recipient_email = input(f"Recipient email (leave blank to use sender): ").strip()
        config["email_notifications"]["recipient_email"] = recipient_email
        
        send_success = input("Send notifications on successful runs? [Y/n]: ").lower()
        config["email_notifications"]["send_on_success"] = not send_success.startswith('n')
        
        send_failure = input("Send notifications on failures? [Y/n]: ").lower()
        config["email_notifications"]["send_on_failure"] = not send_failure.startswith('n')
        
        # Test email configuration
        test_email = input("\nTest email configuration now? [y/N]: ").lower().startswith('y')
        if test_email:
            if test_email_config(config["email_notifications"]):
                print("✓ Email test successful!")
            else:
                print("✗ Email test failed. Check your settings.")
    
    print("\nGIT AUTOMATION SETUP")
    print("-" * 25)
    print("Configure automatic git commit and push.")
    print()
    
    git_enabled = input(f"Enable git automation? [Y/n]: ").lower()
    config["git_automation"]["enabled"] = not git_enabled.startswith('n')
    
    if config["git_automation"]["enabled"]:
        auto_commit = input("Auto-commit changes? [Y/n]: ").lower()
        config["git_automation"]["auto_commit"] = not auto_commit.startswith('n')
        
        auto_push = input("Auto-push to remote? [Y/n]: ").lower()
        config["git_automation"]["auto_push"] = not auto_push.startswith('n')
        
        commit_template = input(f"Commit message template [{config['git_automation']['commit_message_template']}]: ").strip()
        if commit_template:
            config["git_automation"]["commit_message_template"] = commit_template
    
    print("\nPRICE UPDATE SETTINGS")
    print("-" * 25)
    
    timeout = input(f"Timeout per retailer (minutes) [{config['price_update_settings']['timeout_minutes']}]: ").strip()
    if timeout.isdigit():
        config["price_update_settings"]["timeout_minutes"] = int(timeout)
    
    delay = input(f"Delay between retailers (seconds) [{config['price_update_settings']['delay_between_retailers']}]: ").strip()
    if delay.isdigit():
        config["price_update_settings"]["delay_between_retailers"] = int(delay)
    
    print("\nHISTORICAL TRACKING SETUP")
    print("-" * 30)
    
    historical_enabled = input(f"Enable historical price tracking? [Y/n]: ").lower()
    config["historical_tracking"]["enabled"] = not historical_enabled.startswith('n')
    
    if config["historical_tracking"]["enabled"]:
        track_prices = input("Track price changes? [Y/n]: ").lower()
        config["historical_tracking"]["track_price_changes"] = not track_prices.startswith('n')
        
        track_stock = input("Track stock changes? [Y/n]: ").lower()
        config["historical_tracking"]["track_stock_changes"] = not track_stock.startswith('n')
        
        retention = input(f"Data retention (days) [{config['historical_tracking']['retention_days']}]: ").strip()
        if retention.isdigit():
            config["historical_tracking"]["retention_days"] = int(retention)
    
    # Save configuration
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print()
    print("=" * 60)
    print("CONFIGURATION COMPLETE")
    print("=" * 60)
    print(f"Configuration saved to: {config_file.absolute()}")
    print()
    print("Summary:")
    print(f"- Email notifications: {'Enabled' if config['email_notifications']['enabled'] else 'Disabled'}")
    print(f"- Git automation: {'Enabled' if config['git_automation']['enabled'] else 'Disabled'}")
    print(f"- Historical tracking: {'Enabled' if config['historical_tracking']['enabled'] else 'Disabled'}")
    print(f"- Retailer timeout: {config['price_update_settings']['timeout_minutes']} minutes")
    print()
    print("You can now run the automation system with:")
    print("python automated_cigar_price_system.py")
    print()


def test_email_config(email_config):
    """Test email configuration"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        
        if not email_config.get('sender_email') or not email_config.get('sender_password'):
            return False
        
        msg = MIMEText("Test email from Cigar Price Scout automation system.")
        msg['Subject'] = 'Cigar Price Scout - Email Test'
        msg['From'] = email_config['sender_email']
        msg['To'] = email_config.get('recipient_email') or email_config['sender_email']
        
        server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
        server.starttls()
        server.login(email_config['sender_email'], email_config['sender_password'])
        server.send_message(msg)
        server.quit()
        
        return True
        
    except Exception as e:
        print(f"Email test error: {e}")
        return False


if __name__ == "__main__":
    try:
        setup_configuration()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
    except Exception as e:
        print(f"\nSetup failed: {e}")
