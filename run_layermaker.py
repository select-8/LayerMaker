"""Launch the LayerMaker (app2) application."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app2.controller import main

if __name__ == "__main__":
    main()
