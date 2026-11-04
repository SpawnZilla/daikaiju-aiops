#!/usr/bin/env python3
"""Entry point: disarm_authorized_command.py (no arguments)
See kai082_authorized_command_lib.py in this directory for full design
notes and caveats."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kai082_authorized_command_lib import disarm  # noqa: E402

if __name__ == "__main__":
    disarm()
