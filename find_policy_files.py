# find_policy_files.py - Find privacy and terms files
import os
from pathlib import Path

def find_policy_files():
    """Find privacy policy and terms files in the project"""
    
    print("Searching for privacy policy and terms files...")
    print("=" * 60)
    
    # Look for HTML files that might contain policies
    html_files = []
    for root, dirs, files in os.walk("."):
        # Skip common non-relevant directories
        if any(skip_dir in root for skip_dir in ['.git', 'node_modules', '__pycache__', '.venv']):
            continue
            
        for file in files:
            if file.endswith(('.html', '.htm')):
                file_path = os.path.join(root, file)
                html_files.append(file_path)
    
    print(f"Found {len(html_files)} HTML files:")
    for file_path in sorted(html_files):
        print(f"  {file_path}")
    
    print("\n" + "=" * 60)
    
    # Check content of HTML files for policy keywords
    policy_files = []
    terms_files = []
    
    for file_path in html_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                
            if any(keyword in content for keyword in ['privacy policy', 'privacy notice', 'data collection', 'cookies']):
                policy_files.append(file_path)
                
            if any(keyword in content for keyword in ['terms of service', 'terms and conditions', 'user agreement', 'terms of use']):
                terms_files.append(file_path)
                
        except Exception as e:
            print(f"Could not read {file_path}: {e}")
    
    print("PRIVACY POLICY FILES:")
    if policy_files:
        for file_path in policy_files:
            print(f"  FOUND: {file_path}")
    else:
        print("  None found")
    
    print("\nTERMS OF SERVICE FILES:")  
    if terms_files:
        for file_path in terms_files:
            print(f"  FOUND: {file_path}")
    else:
        print("  None found")
    
    print("\n" + "=" * 60)
    print("PROJECT STRUCTURE:")
    
    # Show directory structure
    for root, dirs, files in os.walk("."):
        level = root.replace(".", "").count(os.sep)
        indent = " " * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        
        # Skip deep nested directories
        if level > 3:
            continue
            
        subindent = " " * 2 * (level + 1)
        for file in files[:10]:  # Show only first 10 files per directory
            print(f"{subindent}{file}")
        if len(files) > 10:
            print(f"{subindent}... and {len(files) - 10} more files")

if __name__ == "__main__":
    find_policy_files()