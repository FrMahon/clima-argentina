"""Genera dashboard/argentina.geojson a partir de Natural Earth (dominio público).

Toma las provincias (admin-1) y el contorno del país en la versión con el punto de vista
argentino (incluye Islas Malvinas), descarta las islas del Atlántico Sur lejanas que estiran
el mapa, simplifica las líneas con Douglas-Peucker y redondea coordenadas. Sin dependencias.

Uso:
    python scripts/build_map.py <admin1.geojson> <countries_arg.geojson> [salida]

Archivos de entrada (Natural Earth 10m):
    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries_arg.geojson
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOLERANCE_DEG = 0.02      # ~2 km: invisible a la escala del dashboard
MIN_RING_AREA = 0.004     # grados²: descarta islotes diminutos
MAX_LON = -53.0           # deja afuera Georgias y Sandwich del Sur (Malvinas queda adentro)
DECIMALS = 2

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "dashboard" / "argentina.geojson"


def _perp_dist(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2) ** 0.5


def douglas_peucker(points: list, tol: float) -> list:
    """Versión iterativa (los anillos de Natural Earth tienen miles de puntos)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        best, index = 0.0, -1
        for i in range(start + 1, end):
            d = _perp_dist(points[i], points[start], points[end])
            if d > best:
                best, index = d, i
        if best > tol and index != -1:
            keep[index] = True
            stack += [(start, index), (index, end)]
    return [p for p, k in zip(points, keep) if k]


def ring_area(ring: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2


def simplify_ring(ring: list) -> list | None:
    if ring_area(ring) < MIN_RING_AREA:
        return None
    out = douglas_peucker(ring, TOLERANCE_DEG)
    out = [[round(x, DECIMALS), round(y, DECIMALS)] for x, y in out]
    # quitar duplicados consecutivos que deja el redondeo
    dedup = [out[0]] + [p for prev, p in zip(out, out[1:]) if p != prev]
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    return dedup if len(dedup) >= 4 else None


def simplify_geometry(geom: dict) -> dict | None:
    polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    result = []
    for polygon in polygons:
        outer = polygon[0]
        if max(x for x, _ in outer) > MAX_LON:
            continue
        shell = simplify_ring(outer)
        if shell is None:  # islote: se descarta con sus huecos
            continue
        holes = [h for h in (simplify_ring(r) for r in polygon[1:]) if h]
        result.append([shell, *holes])
    if not result:
        return None
    return {"type": "MultiPolygon", "coordinates": result}


def main(admin1_path: str, country_path: str, out_path: str | None = None) -> None:
    features = []

    admin1 = json.loads(Path(admin1_path).read_text(encoding="utf-8"))
    for f in admin1["features"]:
        if f["properties"].get("adm0_a3") != "ARG":
            continue
        geom = simplify_geometry(f["geometry"])
        if geom:
            features.append({"type": "Feature", "properties": {"kind": "province", "name": f["properties"]["name"]}, "geometry": geom})

    countries = json.loads(Path(country_path).read_text(encoding="utf-8"))
    for f in countries["features"]:
        if f["properties"].get("ADM0_A3") != "ARG":
            continue
        geom = simplify_geometry(f["geometry"])
        if geom:
            features.append({"type": "Feature", "properties": {"kind": "country", "name": "Argentina"}, "geometry": geom})

    out = Path(out_path) if out_path else DEFAULT_OUT
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    n_prov = sum(f["properties"]["kind"] == "province" for f in features)
    print(f"{out}: {n_prov} provincias + contorno, {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
