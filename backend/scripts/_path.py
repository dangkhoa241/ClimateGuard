"""Lets scripts import the climateguard package when run directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Windows consoles default to cp1252, which can't print Vietnamese.
sys.stdout.reconfigure(encoding="utf-8")
