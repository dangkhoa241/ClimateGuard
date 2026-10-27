"""Central config: API keys, model IDs, and the contributor/standard switch."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

BASETEN_API_KEY = os.getenv("BASETEN_API_KEY", "")
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")

BASETEN_BASE_URL = "https://inference.baseten.co/v1"
META_BASE_URL = "https://api.meta.ai/v1"

# Single switch: contributor = cheap, FAKE/dev data only (Meta may train on it).
# Set USE_CONTRIBUTOR=false for real user photos and the live demo.
USE_CONTRIBUTOR = os.getenv("USE_CONTRIBUTOR", "true").strip().lower() in ("1", "true", "yes")

# Model IDs (from https://dev.meta.ai/docs and the Baseten key's model list)
MONITOR_MODEL = "meta-models/muse-spark-open-1026"  # Baseten — exact ID required
CHAT_MODEL = "muse-spark-1.3-contributor" if USE_CONTRIBUTOR else "muse-spark-1.3"
SAM_MODEL = "sam-3.1"
TRANSCRIBE_MODEL = "muse-voice-transcribe-1.0"
IMAGE_MODEL = "muse-image-1.0"

# Default reasoning_effort per provider; override per call with chat(reasoning_effort=...).
# Muse Spark Open accepts low|medium|high|xhigh (Baseten default xhigh; "none" runs as low).
# Muse Spark 1.3 accepts minimal|low|medium|high|xhigh (rejects "none").
# "low" chosen after scripts/compare_effort.py: same decisions as medium/high at 3-7x fewer tokens.
REASONING_EFFORT = {
    "baseten": os.getenv("BASETEN_REASONING_EFFORT", "low"),
    "meta": os.getenv("META_REASONING_EFFORT", "low"),
}

# Response cache TTL (seconds); override per call with chat(cache_ttl=...).
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# --- Data sources ---
# NWS asks for a User-Agent with contact info: https://www.weather.gov/documentation/services-web-api
NWS_USER_AGENT = os.getenv("NWS_USER_AGENT", "ClimateGuard/0.1 (hackathon project)")
# Optional: official EPA AirNow AQI. Without a key we use Open-Meteo's modeled AQI.
AIRNOW_API_KEY = os.getenv("AIRNOW_API_KEY", "")

# --- Storage ---
# "local" = JSON files under LOCAL_DIR (dev); "dynamodb" = the tables below (Lambda).
STORAGE = os.getenv("STORAGE", "local")
SNAPSHOTS_TABLE = os.getenv("SNAPSHOTS_TABLE", "climateguard-snapshots")
USAGE_TABLE = os.getenv("USAGE_TABLE", "climateguard-usage")
CACHE_TABLE = os.getenv("CACHE_TABLE", "climateguard-cache")
ALERTS_TABLE = os.getenv("ALERTS_TABLE", "climateguard-alerts")  # sent alerts + agent decision log

# Local runtime data (gitignored). Lambda sets CG_LOCAL_DIR=/tmp/climateguard (only /tmp is writable).
LOCAL_DIR = Path(os.getenv("CG_LOCAL_DIR", REPO_ROOT / "backend" / ".local"))
USAGE_LOG = LOCAL_DIR / "usage.jsonl"
CACHE_DIR = LOCAL_DIR / "cache"
