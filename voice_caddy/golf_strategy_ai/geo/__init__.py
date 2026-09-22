"""Sottomodulo geodetico e geometrico per golf_strategy_ai."""
from .projection import (
    latlon_to_utm,
    utm_to_latlon,
    to_utm,
    from_utm,
    get_utm_zone,
    get_utm_epsg
)
from .geometry import (
    haversine_distance_m,
    bearing_deg,
    lateral_and_longitudinal_offset,
    calculate_progress_and_offset,
    point_in_polygon,
    polygon_centroid,
    generate_ellipse_points,
    generate_distance_arc
)

__all__ = [
    "latlon_to_utm",
    "utm_to_latlon",
    "to_utm",
    "from_utm",
    "get_utm_zone",
    "get_utm_epsg",
    "haversine_distance_m",
    "bearing_deg",
    "lateral_and_longitudinal_offset",
    "calculate_progress_and_offset",
    "point_in_polygon",
    "polygon_centroid",
    "generate_ellipse_points",
    "generate_distance_arc",
]
