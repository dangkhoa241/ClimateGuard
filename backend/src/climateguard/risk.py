"""Risk math and official thresholds. Environmental risk only, never medical.

Sources:
  Heat index: NWS/WPC Rothfusz regression, https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
  Cal/OSHA outdoor heat (T8 §3395): shade at 80F, high-heat procedures at 95F (air temperature)
  Cal/OSHA wildfire smoke (T8 §5141.1): protections start at AQI 151 for PM2.5
  AQI categories: EPA, https://www.airnow.gov/aqi/aqi-basics/
"""
import math

CALOSHA_SHADE_F = 80
CALOSHA_HIGH_HEAT_F = 95
CALOSHA_SMOKE_AQI = 151

AQI_CATEGORIES = [  # (upper bound inclusive, name)
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (math.inf, "Hazardous"),
]


def heat_index_f(temp_f: float, rh: float) -> float:
    """NWS heat index (F) from air temperature (F) and relative humidity (%)."""
    t, r = temp_f, rh
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + r * 0.094)
    if (simple + t) / 2 < 80:
        return max(simple, t)  # heat index is meaningless in cool weather; never show "feels cooler"
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r
          - 0.00683783 * t * t - 0.05481717 * r * r + 0.00122874 * t * t * r
          + 0.00085282 * t * r * r - 0.00000199 * t * t * r * r)
    if r < 13 and 80 <= t <= 112:
        hi -= ((13 - r) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
    elif r > 85 and 80 <= t <= 87:
        hi += ((r - 85) / 10) * ((87 - t) / 5)
    return hi


def aqi_category(aqi: int | None) -> str | None:
    if aqi is None or aqi < 0:
        return None
    for upper, name in AQI_CATEGORIES:
        if aqi <= upper:
            return name
    return None


def aqi_category_index(aqi: int | None) -> int:
    """0 = Good ... 5 = Hazardous; -1 if unknown. Coarse bucket for change detection."""
    if aqi is None or aqi < 0:
        return -1
    return next(i for i, (upper, _) in enumerate(AQI_CATEGORIES) if aqi <= upper)
