#!/usr/bin/env python3
"""Doppelchatter entry point — run without installing.

Usage:
    python doppel.py chatter
    python doppel.py list
    python doppel.py lint
    python doppel.py export SESSION_ID
    python doppel.py version
"""

import sys
from pathlib import Path

# Add src/ to path for direct execution
sys.path.insert(0, str(Path(__file__).parent / "src"))

from doppelchatter.cli import main

if __name__ == "__main__":
    main()
