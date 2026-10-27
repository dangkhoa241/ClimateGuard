"""NWS event names -> ClimateGuard hazard groups, and the short-fuse exclusion.

ClimateGuard checks conditions every 15 minutes and delivers by email, which is far
too slow for warnings that give minutes of lead time. Those events are EXCLUDED from
alerts (not sent, not used to trigger the agent) and the app points people to
Wireless Emergency Alerts and NOAA Weather Radio instead. Watches for the same
hazards (hours of lead time) are still handled.
"""

# Warnings ClimateGuard never claims to cover. "Emergency" variants are issued as these products.
SHORT_FUSE_EXCLUDED = frozenset({
    "Tornado Warning",
    "Flash Flood Warning",
    "Severe Thunderstorm Warning",
    "Extreme Wind Warning",
})

EXCLUSION_NOTE = ("Tornado, Flash Flood, Severe Thunderstorm and Extreme Wind warnings are not sent by "
                  "ClimateGuard: rely on Wireless Emergency Alerts on your phone and NOAA Weather Radio.")

# Checked in order; first keyword found in the event name wins. Marine-only events never
# match land zones (their UGC codes are marine zones), so they need no group.
_RULES = [
    ("coastal", ("Coastal Flood", "Lakeshore Flood", "Storm Surge", "High Surf", "Rip Current",
                 "Beach Hazards", "Tsunami", "Sneaker Wave")),
    ("tropical", ("Hurricane", "Tropical Storm", "Typhoon", "Tropical Depression")),
    ("tornado", ("Tornado",)),
    ("thunderstorm", ("Severe Thunderstorm", "Severe Weather")),
    ("flood", ("Flood", "Hydrologic")),
    ("heat", ("Heat",)),
    ("winter", ("Winter", "Blizzard", "Ice Storm", "Snow", "Sleet", "Freezing Rain", "Lake Effect")),
    ("cold", ("Cold", "Freeze", "Frost", "Wind Chill", "Hard Freeze")),
    ("fire", ("Red Flag", "Fire Weather", "Fire Warning")),
    ("smoke", ("Air Quality", "Dense Smoke", "Air Stagnation", "Ashfall")),
    ("dust", ("Dust",)),
    ("fog", ("Fog",)),
    ("wind", ("Wind", "Gale")),
]

HAZARD_GROUPS = tuple(g for g, _ in _RULES) + ("other",)


def group_for(event: str) -> str:
    for group, keywords in _RULES:
        if any(k.lower() in event.lower() for k in keywords):
            return group
    return "other"


def is_excluded(event: str) -> bool:
    return event in SHORT_FUSE_EXCLUDED
