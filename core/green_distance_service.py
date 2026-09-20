from __future__ import annotations

import math
import time
import re
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    """Punto geodetico (Latitudine, Longitudine)."""
    lat: float
    lon: float


class GreenCoordinates(BaseModel):
    """
    Struttura dati delle coordinate dei 3 punti di riferimento del green:
    - front: inizio green (bordo frontale verso il giocatore)
    - center: centro geometrico del green
    - back: fondo green (bordo posteriore)
    """
    front: GeoPoint
    center: GeoPoint
    back: GeoPoint


class GreenDistanceResult(BaseModel):
    """Risultato del calcolo delle distanze geodetiche verso il green."""
    hole_number: int
    front_distance: int
    center_distance: int
    back_distance: int
    is_on_green: bool = False
    location_age_seconds: Optional[float] = None
    is_location_stale: bool = False
    has_location: bool = True
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None


# ==============================================================================
# ALGORITMO HAVERSINE GEODETICO (R = 6.371.000 m)
# ==============================================================================

def calculate_geodetic_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Calcola la distanza geodetica del grande cerchio tra due coordinate GPS
    usando la formula di Haversine (Raggio terrestre medio WGS84 = 6.371.000 m).
    Restituisce la distanza arrotondata all'intero più vicino in metri.
    """
    R = 6371000.0  # Raggio terrestre in metri
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return int(round(R * c))


haversine_distance_meters = calculate_geodetic_distance


def derive_front_back_green_points(
    tee_lat: float,
    tee_lon: float,
    center_lat: float,
    center_lon: float,
    front_offset_meters: float = 12.0,
    back_offset_meters: float = 12.0
) -> Tuple[GeoPoint, GeoPoint]:
    """
    Calcola analiticamente i punti Front e Back del green lungo la linea di approccio
    Tee -> Centro Green.
    - front: offset_meters prima del centro (verso il tee)
    - back: offset_meters oltre il centro (allontanandosi dal tee)
    """
    d_total = calculate_geodetic_distance(tee_lat, tee_lon, center_lat, center_lon)
    if d_total <= 0:
        return GeoPoint(lat=center_lat, lon=center_lon), GeoPoint(lat=center_lat, lon=center_lon)

    ratio_front = max(0.0, (d_total - front_offset_meters) / d_total)
    ratio_back = (d_total + back_offset_meters) / d_total

    front_lat = round(tee_lat + (center_lat - tee_lat) * ratio_front, 6)
    front_lon = round(tee_lon + (center_lon - tee_lon) * ratio_front, 6)
    back_lat = round(tee_lat + (center_lat - tee_lat) * ratio_back, 6)
    back_lon = round(tee_lon + (center_lon - tee_lon) * ratio_back, 6)

    return GeoPoint(lat=front_lat, lon=front_lon), GeoPoint(lat=back_lat, lon=back_lon)


# ==============================================================================
# INTENT RECOGNITION COMANDI VOCALI / TESTUALI
# ==============================================================================

DETAILED_PATTERNS = [
    r"\b(?:misure|dettaglio|approfondimento|info)\s+green\b",
    r"\bquanto\s+ho\s+all[\x27\x22]?inizio\b",
    r"\bfront\s+(?:e\s+)?back\b",
    r"\bdistanze\s+complete\b",
    r"\btre\s+distanze\b",
    r"\binizio\s*[,e]?\s*centro\s*[,e]?\s*fondo\b",
    r"\bprofondit[aà]\s+(?:del\s+)?green\b",
    r"^/green\b",
]

RAPID_PATTERNS = [
    r"\bdistanza(?:\s+green|\s+al\s+green|\s+centro|\s+al\s+centro)?\b",
    r"\bquanto\s+(?:ho|manca|c[\x27\x22]è)\b",
    r"\bche\s+distanza\s+c[\x27\x22]è\b",
    r"\bmetri\s+(?:al\s+green|al\s+centro)?\b",
    r"^/distanza\b",
]


def parse_green_distance_intent(text: str) -> Optional[str]:
    """
    Riconosce se il messaggio dell'utente (testo o trascrizione audio) richiede la distanza al green.
    Restituisce:
    - 'DISTANZA_DETTAGLIATA' se richiede Front/Center/Back
    - 'DISTANZA_RAPIDA' per richiesta standard del solo centro
    - None se non pertinente
    """
    clean = text.strip().lower()

    for pat in DETAILED_PATTERNS:
        if re.search(pat, clean):
            return "DISTANZA_DETTAGLIATA"

    for pat in RAPID_PATTERNS:
        if re.search(pat, clean):
            return "DISTANZA_RAPIDA"

    return None


# ==============================================================================
# CALCOLO DISTANZE GREEN & GESTIONE EDGE CASES
# ==============================================================================

def calculate_green_distances(
    user_lat: Optional[float],
    user_lon: Optional[float],
    green_coords: GreenCoordinates,
    hole_number: int = 1,
    location_timestamp: Optional[float] = None,
    max_location_age_seconds: float = 120.0,
    on_green_threshold_meters: int = 15
) -> GreenDistanceResult:
    """
    Calcola le distanze geodetiche verso Front, Center e Back del green.
    Valuta:
    - Presenza posizione GPS (has_location)
    - Freschezza posizione GPS (is_location_stale se > 2 minuti)
    - Prossimità immediata al green (is_on_green se <= 15m dal centro o <= 10m dal front)
    """
    if user_lat is None or user_lon is None:
        return GreenDistanceResult(
            hole_number=hole_number,
            front_distance=0,
            center_distance=0,
            back_distance=0,
            has_location=False
        )

    # Calcolo età posizione GPS
    location_age = None
    is_stale = False
    if location_timestamp is not None and location_timestamp > 0:
        location_age = max(0.0, time.time() - location_timestamp)
        if location_age > max_location_age_seconds:
            is_stale = True

    # Calcolo distanze geodetiche Haversine
    dist_front = calculate_geodetic_distance(user_lat, user_lon, green_coords.front.lat, green_coords.front.lon)
    dist_center = calculate_geodetic_distance(user_lat, user_lon, green_coords.center.lat, green_coords.center.lon)
    dist_back = calculate_geodetic_distance(user_lat, user_lon, green_coords.back.lat, green_coords.back.lon)

    # Controllo se il giocatore si trova sul green
    is_on_green = dist_center <= on_green_threshold_meters or dist_front <= 10

    return GreenDistanceResult(
        hole_number=hole_number,
        front_distance=dist_front,
        center_distance=dist_center,
        back_distance=dist_back,
        is_on_green=is_on_green,
        location_age_seconds=location_age,
        is_location_stale=is_stale,
        has_location=True,
        user_lat=user_lat,
        user_lon=user_lon
    )


# ==============================================================================
# RESPONSE FORMATTERS (TELEGRAM MARKDOWN & TTS SINTESI VOCALE)
# ==============================================================================

def format_distance_response(
    intent: str,
    res: GreenDistanceResult,
    hole_number: int,
    par: int = 4
) -> Tuple[str, str]:
    """
    Formatta la risposta per Telegram e per il sintetizzatore vocale (TTS).
    Restituisce una tupla: (telegram_html_or_markdown, tts_voice_phrase).
    """
    # 1. Edge Case: GPS non attivo
    if not res.has_location:
        telegram_msg = (
            f"📍 <b>Posizione GPS non attiva</b>\n\n"
            f"Per conoscere la distanza esatta dal green della <b>Buca {hole_number}</b>, "
            f"invia la tua posizione Telegram (o attiva la <i>Live Location</i>)."
        )
        voice_msg = "Posizione GPS non attiva. Invia la posizione per calcolare la distanza."
        return telegram_msg, voice_msg

    # 2. Edge Case: GPS scaduto (> 2 minuti)
    if res.is_location_stale:
        minutes = int((res.location_age_seconds or 120) // 60)
        telegram_msg = (
            f"⏱️ <b>Posizione GPS non aggiornata ({minutes} min fa)</b>\n\n"
            f"L'ultimo rilevamento GPS risale a più di 2 minuti fa.\n"
            f"Distanza stimata centro: <b>{res.center_distance}m</b>.\n\n"
            f"📍 <i>Tocca <b>[📍 Calcola Distanza]</b> o aggiorna la posizione per la misura al metro!</i>"
        )
        voice_msg = f"Posizione GPS non aggiornata da più di due minuti. Distanza stimata centro: {res.center_distance} metri."
        return telegram_msg, voice_msg

    # 3. Edge Case: Giocatore già sul green (< 15 metri)
    if res.is_on_green:
        telegram_msg = (
            f"⛳ <b>Sei sul Green della Buca {hole_number}!</b>\n\n"
            f"• <b>Distanza centro:</b> <b>{res.center_distance} metri</b>\n"
            f"<i>Prepara il putter per chiudere la buca.</i>"
        )
        voice_msg = f"Sei sul green, distanza centro: {res.center_distance} metri."
        return telegram_msg, voice_msg

    # 4. MODALITÀ DETTAGLIATA (Front / Center / Back)
    if intent == "DISTANZA_DETTAGLIATA":
        telegram_msg = (
            f"🎯 <b>Misure Green — Buca {hole_number} (Par {par})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Inizio (Front):</b> <b>{res.front_distance}m</b>\n"
            f"⚪ <b>Centro (Center):</b> <b>{res.center_distance}m</b>\n"
            f"🔴 <b>Fondo (Back):</b> <b>{res.back_distance}m</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 <i>Profondità green: {max(0, res.back_distance - res.front_distance)}m</i>"
        )
        voice_msg = f"Inizio {res.front_distance}, centro {res.center_distance}, fondo {res.back_distance} metri."
        return telegram_msg, voice_msg

    # 5. MODALITÀ STANDARD (Rapida: solo Centro Green)
    telegram_msg = (
        f"⛳ <b>Buca {hole_number}:</b> <b>{res.center_distance}m</b> al centro green."
    )
    voice_msg = f"{res.center_distance} metri al centro."
    return telegram_msg, voice_msg
