"""
Issue Resolution System for CigarPriceScout
Tools to help you review and resolve user-reported issues

Usage:
1. Check pending issues: python issue_manager.py list
2. Mark as resolved: python issue_manager.py resolve ISSUE_ID "Fixed price in Fox CSV"
3. View issue details: python issue_manager.py view ISSUE_ID
"""

import csv
import sys
import os
from datetime import datetime

class IssueManager:
    def __init__(self, issues_file="reports/issues/user_reports.csv"):
        self.issues_file = issues_file
        self.ensure_directory()
    
    def ensure_directory(self):
        os.makedirs(os.path.dirname(self.issues_file), exist_ok=True)
    
    def list_issues(self, status_filter=None):
        """List all issues, optionally filtered by status"""
        if not os.path.exists(self.issues_file):
            print("No issues file found.")
            return
        
        with open(self.issues_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            issues = list(reader)
        
        if status_filter:
            issues = [i for i in issues if i.get('status') == status_filter]
        
        if not issues:
            status_msg = f" with status '{status_filter}'" if status_filter else ""
            print(f"No issues found{status_msg}.")
            return
        
        print(f"\n{'ID':<8} {'Date':<12} {'Type':<15} {'Retailer':<20} {'Status':<10}")
        print("-" * 75)
        
        for issue in issues:
            issue_id = issue.get('issue_id', 'N/A')[:8]
            date = issue.get('timestamp', '')[:10]  # YYYY-MM-DD
            issue_type = issue.get('issue_type', '')[:14]
            retailer = issue.get('retailer', '')[:19]
            status = issue.get('status', 'pending')
            
            print(f"{issue_id:<8} {date:<12} {issue_type:<15} {retailer:<20} {status:<10}")
        
        print(f"\nTotal: {len(issues)} issues")
    
    def view_issue(self, issue_id):
        """View detailed information about a specific issue"""
        if not os.path.exists(self.issues_file):
            print("No issues file found.")
            return
        
        with open(self.issues_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for issue in reader:
                if issue.get('issue_id', '').startswith(issue_id):
                    print(f"\n=== ISSUE DETAILS ===")
                    print(f"ID: {issue.get('issue_id')}")
                    print(f"Date: {issue.get('timestamp')}")
                    print(f"Type: {issue.get('issue_type')}")
                    print(f"Retailer: {issue.get('retailer')}")
                    print(f"Product: {issue.get('product_title')}")
                    print(f"URL: {issue.get('product_url')}")
                    print(f"Status: {issue.get('status')}")
                    print(f"Reporter: {issue.get('reporter_email')}")
                    print(f"\nUser Notes:")
                    print(f"{issue.get('notes')}")
                    if issue.get('resolution_notes'):
                        print(f"\nResolution Notes:")
                        print(f"{issue.get('resolution_notes')}")
                    print(f"\n===================")
                    return
        
        print(f"Issue ID '{issue_id}' not found.")
    
    def resolve_issue(self, issue_id, resolution_notes):
        """Mark an issue as resolved with resolution notes"""
        if not os.path.exists(self.issues_file):
            print("No issues file found.")
            return
        
        # Read all issues
        with open(self.issues_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            issues = list(reader)
        
        # Find and update the issue
        found = False
        for issue in issues:
            if issue.get('issue_id', '').startswith(issue_id):
                issue['status'] = 'resolved'
                issue['resolution_notes'] = resolution_notes
                found = True
                print(f"Marked issue {issue.get('issue_id')} as resolved.")
                break
        
        if not found:
            print(f"Issue ID '{issue_id}' not found.")
            return
        
        # Write back to file
        with open(self.issues_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['issue_id', 'timestamp', 'issue_type', 'retailer', 'product_title', 
                         'product_url', 'notes', 'reporter_email', 'status', 'resolution_notes']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(issues)
        
        print("Issue updated successfully.")
    
    def stats(self):
        """Show summary statistics"""
        if not os.path.exists(self.issues_file):
            print("No issues file found.")
            return
        
        with open(self.issues_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            issues = list(reader)
        
        if not issues:
            print("No issues found.")
            return
        
        pending = sum(1 for i in issues if i.get('status') == 'pending')
        resolved = sum(1 for i in issues if i.get('status') == 'resolved')
        
        print(f"\n=== ISSUE STATISTICS ===")
        print(f"Total issues: {len(issues)}")
        print(f"Pending: {pending}")
        print(f"Resolved: {resolved}")
        
        # Issue type breakdown
        types = {}
        for issue in issues:
            issue_type = issue.get('issue_type', 'unknown')
            types[issue_type] = types.get(issue_type, 0) + 1
        
        print(f"\nBy type:")
        for issue_type, count in sorted(types.items()):
            print(f"  {issue_type}: {count}")
        
        print(f"=======================\n")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python issue_manager.py list [pending|resolved]")
        print("  python issue_manager.py view ISSUE_ID")
        print("  python issue_manager.py resolve ISSUE_ID \"Resolution notes\"")
        print("  python issue_manager.py stats")
        return
    
    manager = IssueManager()
    command = sys.argv[1]
    
    if command == 'list':
        status_filter = sys.argv[2] if len(sys.argv) > 2 else None
        manager.list_issues(status_filter)
    
    elif command == 'view':
        if len(sys.argv) < 3:
            print("Usage: python issue_manager.py view ISSUE_ID")
            return
        issue_id = sys.argv[2]
        manager.view_issue(issue_id)
    
    elif command == 'resolve':
        if len(sys.argv) < 4:
            print("Usage: python issue_manager.py resolve ISSUE_ID \"Resolution notes\"")
            return
        issue_id = sys.argv[2]
        resolution_notes = sys.argv[3]
        manager.resolve_issue(issue_id, resolution_notes)
    
    elif command == 'stats':
        manager.stats()
    
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
