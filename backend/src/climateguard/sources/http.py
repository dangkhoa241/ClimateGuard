"""Shared HTTP client: timeouts, a couple of retries on transient errors."""
import time

import requests

from .. import config

_session = requests.Session()
_session.headers["User-Agent"] = config.NWS_USER_AGENT


class SourceError(RuntimeError):
    pass


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: float = 10, retries: int = 2):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code < 500 and resp.status_code != 429:
                resp.raise_for_status()
                return resp.json()
            last = SourceError(f"{resp.status_code} from {url}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last = SourceError(f"{type(e).__name__} from {url}")
        except requests.HTTPError:
            # Never use str(e): it contains the full URL, query string included (API keys!).
            # Error text ends up in snapshots, which the public API serves.
            raise SourceError(f"{resp.status_code} {resp.reason} from {url}") from None
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise last
