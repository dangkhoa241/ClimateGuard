"""Cities we monitor: Stockton plus nearby Central Valley farm towns."""

TIMEZONE = "America/Los_Angeles"

CITIES = {
    "stockton": {"name": "Stockton", "lat": 37.9577, "lon": -121.2908},
    "lodi": {"name": "Lodi", "lat": 38.1302, "lon": -121.2724},
    "manteca": {"name": "Manteca", "lat": 37.7974, "lon": -121.2161},
    "tracy": {"name": "Tracy", "lat": 37.7397, "lon": -121.4252},
    "modesto": {"name": "Modesto", "lat": 37.6391, "lon": -120.9969},
    "merced": {"name": "Merced", "lat": 37.3022, "lon": -120.4830},
}


def get_city(slug: str) -> dict:
    try:
        return {"slug": slug, **CITIES[slug]}
    except KeyError:
        raise ValueError(f"unknown city {slug!r}; known: {', '.join(CITIES)}") from None
