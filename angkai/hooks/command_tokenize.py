#!/usr/bin/env python3
import shlex
import sys

if len(sys.argv) != 2:
    sys.exit(0)

try:
    parts = shlex.split(sys.argv[1])
except ValueError:
    sys.exit(0)

for p in parts:
    sys.stdout.write(p + "\0")
