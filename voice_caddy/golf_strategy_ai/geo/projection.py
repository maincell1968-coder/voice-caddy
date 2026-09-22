from __future__ import annotations

import math
from typing import Tuple, Optional

# Costanti Ellissoide WGS84 standard
WGS84_A = 6378137.0          # Semiasse maggiore in metri
WGS84_F = 1.0 / 298.257223563  # Schiacciamento
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_E2 = (WGS84_A**2 - WGS84_B**2) / (WGS84_A**2)
WGS84_E_PRIME2 = (WGS84_A**2 - WGS84_B**2) / (WGS84_B**2)
UTM_K0 = 0.9996


def get_utm_zone(lon: float) -> int:
    """Restituisce il fuso UTM (1-60) per una determinata longitudine."""
    return int((lon + 180.0) / 6.0) + 1


def get_utm_epsg(lat: float, lon: float) -> int:
    """Restituisce il codice EPSG ufficiale per la zona UTM corrispondente."""
    zone = get_utm_zone(lon)
    return (32600 + zone) if lat >= 0 else (32700 + zone)


def latlon_to_utm(lat: float, lon: float, zone: Optional[int] = None) -> Tuple[float, float, int, str]:
    """
    Converte coordinate geografiche WGS84 (lat, lon in gradi decimali)
    in coordinate metriche piane UTM (Easting, Northing in metri).
    Formula esatta Transverse Mercator (WGS84).
    Ritorna: (easting_m, northing_m, zone, hemisphere)
    """
    if zone is None:
        zone = get_utm_zone(lon)

    hemisphere = "N" if lat >= 0 else "S"
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    # Longitudine del meridiano centrale della zona UTM
    lon0 = math.radians((zone - 1) * 6.0 - 180.0 + 3.0)

    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(lat_rad)**2)
    t = math.tan(lat_rad)**2
    c = WGS84_E_PRIME2 * math.cos(lat_rad)**2
    a_term = math.cos(lat_rad) * (lon_rad - lon0)

    # Lunghezza dell'arco di meridiano (M)
    m = WGS84_A * (
        (1.0 - WGS84_E2 / 4.0 - 3.0 * WGS84_E2**2 / 64.0 - 5.0 * WGS84_E2**3 / 256.0) * lat_rad
        - (3.0 * WGS84_E2 / 8.0 + 3.0 * WGS84_E2**2 / 32.0 + 45.0 * WGS84_E2**3 / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * WGS84_E2**2 / 256.0 + 45.0 * WGS84_E2**3 / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * WGS84_E2**3 / 3072.0) * math.sin(6.0 * lat_rad)
    )

    easting = UTM_K0 * n * (
        a_term + (1.0 - t + c) * a_term**3 / 6.0
        + (5.0 - 18.0 * t + t**2 + 72.0 * c - 58.0 * WGS84_E_PRIME2) * a_term**5 / 120.0
    ) + 500000.0

    northing = UTM_K0 * (
        m + n * math.tan(lat_rad) * (
            a_term**2 / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c**2) * a_term**4 / 24.0
            + (61.0 - 58.0 * t + t**2 + 600.0 * c - 330.0 * WGS84_E_PRIME2) * a_term**6 / 720.0
        )
    )

    if lat < 0:
        northing += 10000000.0

    return round(easting, 3), round(northing, 3), zone, hemisphere


def utm_to_latlon(easting: float, northing: float, zone: int, hemisphere: str = "N") -> Tuple[float, float]:
    """
    Converte coordinate piane UTM (Easting, Northing in metri)
    nelle corrispondenti coordinate geografiche WGS84 (lat, lon in gradi decimali).
    """
    x = easting - 500000.0
    y = northing if hemisphere.upper() == "N" else northing - 10000000.0

    m = y / UTM_K0
    mu = m / (WGS84_A * (1.0 - WGS84_E2 / 4.0 - 3.0 * WGS84_E2**2 / 64.0 - 5.0 * WGS84_E2**3 / 256.0))

    e1 = (1.0 - math.sqrt(1.0 - WGS84_E2)) / (1.0 + math.sqrt(1.0 - WGS84_E2))

    phi1 = mu + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu) \
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu) \
        + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu) \
        + (1097.0 * e1**4 / 512.0) * math.sin(8.0 * mu)

    n1 = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(phi1)**2)
    t1 = math.tan(phi1)**2
    c1 = WGS84_E_PRIME2 * math.cos(phi1)**2
    r1 = WGS84_A * (1.0 - WGS84_E2) / ((1.0 - WGS84_E2 * math.sin(phi1)**2)**1.5)
    d = x / (n1 * UTM_K0)

    lat_rad = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * WGS84_E_PRIME2) * d**4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1**2 - 252.0 * WGS84_E_PRIME2 - 3.0 * c1**2) * d**6 / 720.0
    )

    lon0 = math.radians((zone - 1) * 6.0 - 180.0 + 3.0)
    lon_rad = lon0 + (
        d - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1**2 + 8.0 * WGS84_E_PRIME2 + 24.0 * t1**2) * d**5 / 120.0
    ) / math.cos(phi1)

    return round(math.degrees(lat_rad), 7), round(math.degrees(lon_rad), 7)


# Alias per brevità di utilizzo
to_utm = latlon_to_utm
from_utm = utm_to_latlon
