"""ZIP code and coordinate handling. No network: ZIPs come from the bundled Census file.

data/zcta.csv.gz: 2024 Census Gazetteer ZIP Code Tabulation Areas (internal points),
https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
"""
import csv
import gzip
import re
from functools import lru_cache
from pathlib import Path

ZCTA_PATH = Path(__file__).parent / "data" / "zcta.csv.gz"
ZIP_RE = re.compile(r"^\d{5}$")


class GeoError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@lru_cache(maxsize=1)
def _zips() -> dict[str, tuple[float, float]]:
    with gzip.open(ZCTA_PATH, "rt", encoding="utf-8") as f:
        return {r["zip"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}


def zip_to_point(zip_code: str) -> tuple[float, float]:
    z = (zip_code or "").strip()[:5]
    if not ZIP_RE.match(z):
        raise GeoError("invalid_zip")
    try:
        return _zips()[z]
    except KeyError:
        raise GeoError("unknown_zip") from None


def coarse_point(lat, lon) -> tuple[float, float]:
    """Validate browser coordinates and round to 2 decimals (~1 km): enough for an NWS
    forecast zone, and we never store anything more precise."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise GeoError("invalid_location") from None
    # Generous US box (incl. Alaska, Hawaii, territories); NWS rejects anything it doesn't cover.
    if not (13.0 <= lat <= 72.0 and -180.0 <= lon <= -64.0):
        raise GeoError("outside_us")
    return round(lat, 2), round(lon, 2)
