"""Open-Meteo weather plugin with real endpoint verification."""

import asyncio
import httpx
from typing import Any, Dict

from app.config import Settings
from app.tools.registry import BaseTool

# WMO weather codes (source: https://open-meteo.com/en/docs)
WEATHER_CODE_MAP: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Moderate showers",
    82: "Heavy showers",
    85: "Light snow showers",
    86: "Moderate/heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light rain",
    99: "Thunderstorm with heavy rain",
}


class Weather(BaseTool):
    name = "weather"

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._geocode_cache: Dict[str, Dict[str, float]] = {}

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Get current weather and forecast for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or 'default' for settings default",
                    },
                },
                "required": ["location"],
            },
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        location = args.get("location", "default")
        if location == "default":
            lat, lon = self.settings.weather_default_lat, self.settings.weather_default_lon
        else:
            lat, lon = await self._geocode(location, timeout_s)
            if lat is None:
                return {"ok": False, "error": "Location not found"}

        return await self._fetch_weather(lat, lon, timeout_s)

    async def _geocode(self, location: str, timeout_s: float) -> tuple[float | None, float | None]:
        """Geocode location via Open-Meteo (cache in-memory)."""
        if location in self._geocode_cache:
            return self._geocode_cache[location].get("lat"), self._geocode_cache[location].get("lon")

        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": location, "count": 1}
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("results"):
                    return None, None
                first = data["results"][0]
                self._geocode_cache[location] = {
                    "lat": first["latitude"],
                    "lon": first["longitude"],
                }
                return first["latitude"], first["longitude"]
        except Exception as e:
            return None, None

    async def _fetch_weather(self, lat: float, lon: float, timeout_s: float) -> Dict[str, Any]:
        """Fetch current + daily forecast (verified endpoints)."""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 2,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                current = data["current"]
                daily = data["daily"]

                # Map weather_code to human text
                code = current["weather_code"]
                weather_text = WEATHER_CODE_MAP.get(code, f"Code {code}")

                return {
                    "ok": True,
                    "current": {
                        "temperature": current["temperature_2m"],
                        "humidity": current["relative_humidity_2m"],
                        "weather": weather_text,
                        "wind_speed": current["wind_speed_10m"],
                    },
                    "forecast": [
                        {
                            "date": daily["time"][0],
                            "high": daily["temperature_2m_max"][0],
                            "low": daily["temperature_2m_min"][0],
                        },
                        {
                            "date": daily["time"][1],
                            "high": daily["temperature_2m_max"][1],
                            "low": daily["temperature_2m_min"][1],
                        },
                    ],
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}