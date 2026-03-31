"""Launch the LayerConfig (json_generator) application."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from json_generator.app import main

if __name__ == "__main__":
    main()
