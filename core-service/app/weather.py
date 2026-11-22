"""Anti-corruption layer untuk Open-Meteo.

Hanya file ini yang tahu format JSON Open-Meteo. Bagian lain sistem hanya
memakai DayCondition dari domain.py.
"""
import time

import httpx

from .domain import DayCondition

URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "TugasBesar-TST/1.0 (kelompok-unayaha)"
CACHE_TTL_SECONDS = 3600
_cache: dict[tuple, tuple[float, list[DayCondition]]] = {}


class WeatherUnavailable(Exception):
    """Open-Meteo tidak bisa dihubungi / respons tidak sesuai."""


def fetch_forecast(lat: float, lon: float, days: int = 7) -> list[DayCondition]:
    key = (round(lat, 2), round(lon, 2), days)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum,relative_humidity_2m_mean",
        "forecast_days": days,
        "timezone": "auto",
    }
    try:
        resp = httpx.get(URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        daily = resp.json()["daily"]
        result = [
            DayCondition(date=d, humidity_mean=h or 0.0, rain_mm=p or 0.0)
            for d, h, p in zip(
                daily["time"], daily["relative_humidity_2m_mean"], daily["precipitation_sum"]
            )
        ]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise WeatherUnavailable(str(exc)) from exc

    _cache[key] = (time.time(), result)
    return result
