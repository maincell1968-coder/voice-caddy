from __future__ import annotations

import time
import json
import logging
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Mappatura WMO Weather Code
WMO_WEATHER_CODES = {
    0: ("Sereno", "☀️"),
    1: ("Prevalentemente sereno", "🌤️"),
    2: ("Parzialmente nuvoloso", "⛅"),
    3: ("Coperto", "☁️"),
    45: ("Nebbia", "🌫️"),
    48: ("Nebbia con brina", "🌫️"),
    51: ("Pioggerella leggera", "🌦️"),
    53: ("Pioggerella moderata", "🌦️"),
    55: ("Pioggerella densa", "🌧️"),
    56: ("Pioggerella gelata", "🌧️"),
    57: ("Pioggerella gelata densa", "🌧️"),
    61: ("Pioggia debole", "🌧️"),
    63: ("Pioggia moderata", "🌧️"),
    65: ("Pioggia forte", "🌧️"),
    66: ("Pioggia gelata leggera", "🌧️"),
    67: ("Pioggia gelata intensa", "🌧️"),
    71: ("Nevicata debole", "❄️"),
    73: ("Nevicata moderata", "❄️"),
    75: ("Nevicata forte", "❄️"),
    77: ("Granelli di neve", "❄️"),
    80: ("Rovesci di pioggia deboli", "🌦️"),
    81: ("Rovesci di pioggia moderati", "🌧️"),
    82: ("Rovesci di pioggia violenti", "🌧️"),
    85: ("Rovesci di neve deboli", "❄️"),
    86: ("Rovesci di neve intensi", "❄️"),
    95: ("Temporale", "⛈️"),
    96: ("Temporale con grandine debole", "⛈️"),
    99: ("Temporale con grandine forte", "⛈️")
}


def degrees_to_cardinal_and_arrow(deg: float) -> Tuple[str, str]:
    """
    Converte i gradi della direzione del vento (0°-360°) nella rosa dei venti
    con relativa emoji direzionale (freccia con direzione del vettore di flusso):
    338° - 22°: N (⬇️ verso Sud)
    23° - 67°: NE (↙️ verso Sud-Ovest)
    68° - 112°: E (⬅️ verso Ovest)
    113° - 157°: SE (↖️ verso Nord-Ovest)
    158° - 202°: S (⬆️ verso Nord)
    203° - 247°: SO (↗️ verso Nord-Est)
    248° - 292°: O (➡️ verso Est)
    293° - 337°: NO (↘️ verso Sud-Est)
    """
    normalized = float(deg) % 360.0

    if normalized >= 337.5 or normalized < 22.5:
        return "N", "⬇️"
    elif 22.5 <= normalized < 67.5:
        return "NE", "↙️"
    elif 67.5 <= normalized < 112.5:
        return "E", "⬅️"
    elif 112.5 <= normalized < 157.5:
        return "SE", "↖️"
    elif 157.5 <= normalized < 202.5:
        return "S", "⬆️"
    elif 202.5 <= normalized < 247.5:
        return "SO", "↗️"
    elif 247.5 <= normalized < 292.5:
        return "O", "➡️"
    else:  # 292.5 <= normalized < 337.5
        return "NO", "↘️"


class WeatherService:
    """
    Servizio di monitoraggio meteo e vento sul percorso da golf.
    Utilizza l'API aperta gratuita di Open-Meteo senza necessità di API Key,
    con cache in memoria a tempo (TTL 10 min) per ridurre la latenza e prevenire rate limiting.
    """

    def __init__(self, cache_ttl_seconds: int = 600):
        self.cache_ttl = cache_ttl_seconds
        # Cache: (round(lat, 3), round(lon, 3)) -> (timestamp, data_dict)
        self._cache: Dict[Tuple[float, float], Tuple[float, Dict[str, Any]]] = {}

    def get_current_weather(self, lat: float, lon: float, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Recupera le condizioni meteo e vento attuali da Open-Meteo:
        - temperatura a 2m (°C)
        - umidità relativa (%)
        - weather_code e descrizione
        - velocità media del vento (km/h)
        - direzione vento in gradi, sigla cardinale ed emoji freccia flusso
        - raffiche di vento (km/h)
        """
        cache_key = (round(lat, 3), round(lon, 3))
        now = time.time()

        if cache_key in self._cache:
            ts, cached_data = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return cached_data

        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m&"
            f"wind_speed_unit=kmh&timezone=auto"
        )

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "VoiceCaddyGolf/1.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))

            current = data.get("current", {})
            temp = float(current.get("temperature_2m", 20.0))
            humidity = int(current.get("relative_humidity_2m", 50))
            w_code = int(current.get("weather_code", 0))
            w_speed = float(current.get("wind_speed_10m", 0.0))
            w_deg = float(current.get("wind_direction_10m", 0.0))
            w_gusts = float(current.get("wind_gusts_10m", w_speed))

            cardinal, arrow = degrees_to_cardinal_and_arrow(w_deg)
            desc, emoji = WMO_WEATHER_CODES.get(w_code, ("Variabile", "⛅"))

            result = {
                "temperature": round(temp, 1),
                "humidity": humidity,
                "weather_code": w_code,
                "weather_desc": f"{desc} {emoji}".strip(),
                "weather_condition": desc,
                "weather_emoji": emoji,
                "wind_speed": round(w_speed, 1),
                "wind_direction_deg": int(round(w_deg)),
                "wind_cardinal": cardinal,
                "wind_arrow": arrow,
                "wind_gusts": round(w_gusts, 1),
                "is_live": True
            }

            self._cache[cache_key] = (now, result)
            return result

        except Exception as e:
            logger.warning(f"Errore recupero meteo da Open-Meteo ({lat}, {lon}): {e}")
            # Fallback di sicurezza per non bloccare mai il giocatore
            return {
                "temperature": 21.0,
                "humidity": 55,
                "weather_code": 0,
                "weather_desc": "Sereno ☀️",
                "weather_condition": "Sereno",
                "weather_emoji": "☀️",
                "wind_speed": 10.0,
                "wind_direction_deg": 180,
                "wind_cardinal": "S",
                "wind_arrow": "⬆️",
                "wind_gusts": 15.0,
                "is_live": False
            }


weather_service = WeatherService()
