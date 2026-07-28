"""
weather.py
Current weather + short forecast using Open-Meteo (free, no API key).
"""
import requests

from utils import get_logger

log = get_logger("weather")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


def _geocode(city: str):
    r = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=10)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    top = results[0]
    return top["latitude"], top["longitude"], top.get("name", city), top.get("country", "")


def get_weather(city: str) -> str:
    """Return a spoken/printed one-liner with the current weather for `city`."""
    try:
        geo = _geocode(city)
        if not geo:
            return f"I couldn't find a place called {city}."
        lat, lon, resolved_name, country = geo

        r = requests.get(FORECAST_URL, params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
            "timezone": "auto",
        }, timeout=10)
        r.raise_for_status()
        cur = r.json().get("current", {})

        temp = cur.get("temperature_2m")
        feels = cur.get("apparent_temperature")
        humidity = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        code = cur.get("weather_code")
        desc = WEATHER_CODES.get(code, "unusual conditions")

        return (f"It's currently {temp}°C ({desc}) in {resolved_name}, {country}, "
                f"feels like {feels}°C, humidity {humidity}%, wind {wind} km/h.")
    except requests.RequestException as e:
        log.warning("weather lookup failed: %s", e)
        return "I couldn't reach the weather service right now — check your internet connection."


def get_forecast(city: str, days: int = 3) -> str:
    try:
        geo = _geocode(city)
        if not geo:
            return f"I couldn't find a place called {city}."
        lat, lon, resolved_name, country = geo

        r = requests.get(FORECAST_URL, params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto",
            "forecast_days": max(1, min(days, 7)),
        }, timeout=10)
        r.raise_for_status()
        daily = r.json().get("daily", {})

        lines = [f"{days}-day forecast for {resolved_name}, {country}:"]
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        for d, hi, lo, c in zip(dates, highs, lows, codes):
            lines.append(f"  {d}: {WEATHER_CODES.get(c, 'mixed conditions')}, high {hi}°C / low {lo}°C")
        return "\n".join(lines)
    except requests.RequestException as e:
        log.warning("forecast lookup failed: %s", e)
        return "I couldn't reach the weather service right now."
