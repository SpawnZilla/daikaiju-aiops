"""Put the Mokaima adapter code on sys.path so pytest finds it from a fresh checkout."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mokaima-adapter"))
