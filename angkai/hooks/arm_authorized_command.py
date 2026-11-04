#!/usr/bin/env python3
"""Entry point: arm_authorized_command.py <task_id> "<exact bash command>" ["<health-check command>"]
See kai082_authorized_command_lib.py in this directory for full design
notes, caveats, and the session-restart requirement. The 3rd argument
is optional -- if given, enables auto-rollback on that
health-check's failure after the armed command runs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kai082_authorized_command_lib import arm  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: arm_authorized_command.py <task_id> \"<exact bash command>\" [\"<health-check command>\"]")
        sys.exit(1)
    health_check = sys.argv[3] if len(sys.argv) == 4 else None
    arm(sys.argv[1], sys.argv[2], health_check)
