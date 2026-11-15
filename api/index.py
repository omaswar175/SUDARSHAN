import os
import sys

# Ensure root directory is in Python path so 'app.py' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app