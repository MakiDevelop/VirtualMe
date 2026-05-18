"""Pytest configuration: put src/ on sys.path so `from virtualme.* import *`
works without requiring `pip install -e .` first.

This lets contributors clone the repo and run `pytest` immediately.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("VIRTUALME_CONSENT_REQUIRED", "false")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
