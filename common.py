
"""Shared helpers: settings, weather API calls, and the CSV log."""
import csv
import os
import time
import random
import requests

def env(name, default):
    """Read a setting. Empty values count as unset (GitHub passes empty strings)."""
    return os.getenv(name) or default

CITY = env("CITY", "Belfast")
LAT = float(env("LAT", "54.5973"))
LON = float(env("LON", "-5.9301"))
TIMEZONE = env("TIMEZONE", "Europe/London")
LOG_PATH = env("LOG_PATH", "data/weather_log.csv")

FIELDS = [
    "date", "city", "temp_max_c", "temp_min_c", "rain_mm",
    "rain_chance_pct", "wind_max_kmh", "weather_code", "briefing"
]

WMO = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy",
    3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "light showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorm"
}

def get_weather(past_days=0, forecast_days=3):
    """Get daily weather from Open-Meteo with automatic retries."""

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TIMEZONE,
        "past_days": past_days,
        "forecast_days": forecast_days,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,weather_code"
        ),
    }

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            print(
                f"Open-Meteo request: attempt {attempt}/{max_attempts}",
                flush=True
            )

            response = requests.get(
                url,
                params=params,
                timeout=(10, 45)
            )

            response.raise_for_status()
            d = response.json()["daily"]

            out = []

            for i, day in enumerate(d["time"]):
                code = d["weather_code"][i]

                out.append({
                    "date": day,
                    "temp_max_c": d["temperature_2m_max"][i],
                    "temp_min_c": d["temperature_2m_min"][i],
                    "rain_mm": d["precipitation_sum"][i],
                    "rain_chance_pct": d["precipitation_probability_max"][i],
                    "wind_max_kmh": d["wind_speed_10m_max"][i],
                    "weather_code": code,
                    "conditions": WMO.get(code, "mixed conditions"),
                })

            print("Open-Meteo request successful.", flush=True)
            return out

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as error:

            print(
                f"Temporary Open-Meteo connection issue: {error}",
                flush=True
            )

            if attempt == max_attempts:
                raise RuntimeError(
                    f"Open-Meteo unavailable after {max_attempts} attempts"
                ) from error

        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else None

            if status not in (429, 500, 502, 503, 504) or attempt == max_attempts:
                raise

            print(f"Open-Meteo HTTP {status}; retrying.", flush=True)

        if attempt < max_attempts:
            delay = min(2 ** attempt, 10) + random.uniform(0, 1)
            print(f"Waiting {delay:.1f} seconds before retry.", flush=True)
            time.sleep(delay)

    raise RuntimeError("Open-Meteo request failed")


def read_log():
    try:
        with open(LOG_PATH, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def upsert_rows(new_rows):
    """Add or replace rows by (date, city). Keeps an existing briefing if the new row has none."""

    rows = {(r["date"], r["city"]): r for r in read_log()}

    for n in new_rows:
        key = (n["date"], n["city"])
        old = rows.get(key, {})

        row = {k: n.get(k, "") for k in FIELDS}

        if not row["briefing"]:
            row["briefing"] = old.get("briefing", "")

        rows[key] = row

    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)

    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()

        for key in sorted(rows):
            w.writerow(rows[key])
