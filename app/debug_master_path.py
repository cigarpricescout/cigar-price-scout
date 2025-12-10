"""
Debug script to find master_cigars.csv location
Run this from your app directory to see actual file structure
"""

import os
import sys

print("=== DEBUGGING FILE PATHS ===")
print(f"Current working directory: {os.getcwd()}")
print(f"Script location: {__file__}")
print(f"Script directory: {os.path.dirname(__file__)}")

# Check different possible locations
possible_paths = [
    "../data/master_cigars.csv",
    "data/master_cigars.csv", 
    "../master_cigars.csv",
    "master_cigars.csv",
    "../../data/master_cigars.csv",
    "../static/data/master_cigars.csv"
]

print(f"\n=== CHECKING POSSIBLE MASTER FILE LOCATIONS ===")
for path in possible_paths:
    full_path = os.path.abspath(path)
    exists = os.path.exists(path)
    print(f"{path:30} -> {full_path} [{'EXISTS' if exists else 'NOT FOUND'}]")
    if exists:
        try:
            with open(path, 'r') as f:
                line_count = sum(1 for _ in f)
            print(f"                              -> {line_count} lines in file")
        except:
            print(f"                              -> Could not read file")

# Also check what's actually in parent directories
print(f"\n=== DIRECTORY CONTENTS ===")
try:
    print(f"Current directory contents: {os.listdir('.')}")
except:
    pass

try:
    print(f"Parent directory contents: {os.listdir('..')}")
except:
    pass

try:
    print(f"../data contents: {os.listdir('../data')}")
except:
    print(f"../data directory does not exist")

try:
    print(f"../static contents: {os.listdir('../static')}")
except:
    print(f"../static directory does not exist")
