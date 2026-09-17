from __future__ import annotations

import math
import json
import logging
import urllib.request
import urllib.parse
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcola la distanza orizzontale del grande cerchio tra due coordinate GPS
    (lat1, lon1) e (lat2, lon2) in metri usando la formula di Haversine.
    """
    R = 6371000.0  # Raggio medio terrestre in metri
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


def calculate_plays_like(horizontal_dist: float, elevation_diff: float, slope_factor: float = 1.0) -> float:
    """
    Calcola la distanza effettiva balistica da golf ("Plays Like Distance"):
    d_plays_like = Delta d + (Delta h * c)
    - Delta d: distanza orizzontale in metri
    - Delta h = h_green - h_ball (positivo = salita / richiede più bastone, negativo = discesa / richiede meno bastone)
    - c: fattore balistico empirico golfistico standard (~0.9 - 1.0; 10m di salita richiedono ~10m in più)
    """
    return round(horizontal_dist + (elevation_diff * slope_factor), 1)


def get_slope_label(elevation_diff: float, threshold: float = 1.5) -> str:
    """Restituisce l'etichetta testuale della pendenza (Salita, Discesa o Pianura)."""
    if elevation_diff >= threshold:
        return "Salita"
    elif elevation_diff <= -threshold:
        return "Discesa"
    else:
        return "Pianura"


class ElevationService:
    """
    Servizio di lookup altimetrico con supporto a API gratuite aperte (Open-Meteo & Open-Elevation)
    con cache locale in memoria e gestione robusta di timeout e graceful fallback.
    """

    def __init__(self):
        # Cache coordinate: (round(lat, 4), round(lon, 4)) -> elevation_meters
        self._cache: Dict[Tuple[float, float], float] = {}

    def get_elevation(self, lat: float, lon: float, timeout: float = 4.0) -> Optional[float]:
        """
        Ottiene l'altitudine in metri sul livello del mare per una coppia di coordinate GPS.
        Cerca prima in cache locale; se assente, interroga Open-Meteo Elevation API con
        fallback su Open-Elevation API.
        """
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Prova Open-Meteo Elevation API (gratuita, velocissima, no-auth)
        try:
            url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
            req = urllib.request.Request(url, headers={"User-Agent": "VoiceCaddy/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "elevation" in data and isinstance(data["elevation"], list) and len(data["elevation"]) > 0:
                    alt = float(data["elevation"][0])
                    self._cache[cache_key] = alt
                    return alt
        except Exception as e:
            logger.warning(f"Lookup Open-Meteo fallito ({lat}, {lon}): {e}")

        # 2. Fallback su Open-Elevation API
        try:
            url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
            req = urllib.request.Request(url, headers={"User-Agent": "VoiceCaddy/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "results" in data and len(data["results"]) > 0:
                    alt = float(data["results"][0]["elevation"])
                    self._cache[cache_key] = alt
                    return alt
        except Exception as e:
            logger.warning(f"Lookup Open-Elevation fallito ({lat}, {lon}): {e}")

        return None

    def calculate_hole_approach(
        self,
        ball_lat: float,
        ball_lon: float,
        target_lat: float,
        target_lon: float,
        ball_altitude: Optional[float] = None,
        target_altitude: Optional[float] = None,
        slope_factor: float = 1.0,
        fallback_elevation_diff: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcola i parametri completi di approccio al green/pin:
        - raw_distance: distanza orizzontale in linea d'aria (Haversine)
        - elevation_diff: dislivello (h_target - h_ball)
        - plays_like_distance: distanza balistica effettiva corretta
        - slope_label: "Salita", "Discesa", "Pianura" o "Quota N/D"
        - ball_altitude: quota rilevata della palla
        - target_altitude: quota rilevata del green/pin
        """
        horizontal_dist = haversine_distance(ball_lat, ball_lon, target_lat, target_lon)

        # Risolvi quota palla
        b_alt = ball_altitude
        if b_alt is None:
            b_alt = self.get_elevation(ball_lat, ball_lon)

        # Risolvi quota green
        t_alt = target_altitude
        if t_alt is None:
            t_alt = self.get_elevation(target_lat, target_lon)

        if b_alt is not None and t_alt is not None:
            elevation_diff = round(t_alt - b_alt, 1)
            plays_like = calculate_plays_like(horizontal_dist, elevation_diff, slope_factor)
            slope_label = get_slope_label(elevation_diff)
        elif fallback_elevation_diff is not None:
            # Fallback euristico dal profilo orografico della buca
            elevation_diff = round(fallback_elevation_diff, 1)
            plays_like = calculate_plays_like(horizontal_dist, elevation_diff, slope_factor)
            slope_label = f"{get_slope_label(elevation_diff)} (Stima orografica)"
        else:
            # Graceful fallback: nessuna quota disponibile -> solo distanza orizzontale
            elevation_diff = 0.0
            plays_like = horizontal_dist
            slope_label = "Piana (Quota N/D)"

        return {
            "raw_distance": horizontal_dist,
            "elevation_diff": elevation_diff,
            "plays_like_distance": plays_like,
            "slope_label": slope_label,
            "ball_altitude": b_alt,
            "target_altitude": t_alt
        }


# Singleton instance
elevation_service = ElevationService()
