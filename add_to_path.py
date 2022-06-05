import os, sys

def add_to_path(path):  
    # Convert to absolute path
    absolute_path = os.path.abspath(path)
    if absolute_path not in sys.path:
        sys.path.append(absolute_path)