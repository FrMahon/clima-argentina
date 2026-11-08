"""Grilla del mapa de calor: qué celdas de 0,5° caen dentro de Argentina.

Las celdas dependen solo del contorno del país, que no cambia, así que se calculan una vez
(`python -m clima.heatgrid`) y se guardan en dashboard/heat-grid.json. Hacerlo en el navegador
de cada visitante costaba ~2,5 s de pantalla congelada al activar el mapa de calor.

Point-in-polygon plano (ray casting) sobre lon/lat: para celdas de 0,5° la diferencia con el
cálculo esférico es despreciable, y la capa se recorta igual al contorno exacto al dibujarla.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

STEP_DEG = 0.5
BBOX = (-74.0, -56.0, -53.0, -21.0)  # oeste, sur, este, norte
MAP_PATH = config.DASHBOARD_DIR / "argentina.geojson"
GRID_PATH = config.DASHBOARD_DIR / "heat-grid.json"


def _in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _bbox(ring: list) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _polygons(geometry: dict) -> list:
    return geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]


def point_in_geometry(point: tuple[float, float], geometry: dict) -> bool:
    """Dentro del anillo exterior y fuera de sus huecos, en cualquiera de los polígonos."""
    x, y = point
    for polygon in _polygons(geometry):
        x0, y0, x1, y1 = _bbox(polygon[0])
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        if _in_ring(x, y, polygon[0]) and not any(_in_ring(x, y, hole) for hole in polygon[1:]):
            return True
    return False


def build_cells(geometry: dict, bbox: tuple = BBOX, step: float = STEP_DEG) -> list[list[float]]:
    """Esquina suroeste [lon, lat] de cada celda que toca el polígono (centro o alguna esquina adentro)."""
    west, south, east, north = bbox
    n_lon = round((east - west) / step)
    n_lat = round((north - south) / step)
    cells = []
    for i in range(n_lon):
        lon = west + i * step
        for j in range(n_lat):
            lat = south + j * step
            probes = [
                (lon + step / 2, lat + step / 2),
                (lon, lat), (lon + step, lat), (lon + step, lat + step), (lon, lat + step),
            ]
            if any(point_in_geometry(p, geometry) for p in probes):
                cells.append([round(lon, 2), round(lat, 2)])
    return cells


def main() -> None:
    geo = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    country = next(f for f in geo["features"] if f["properties"]["kind"] == "country")
    cells = build_cells(country["geometry"])
    GRID_PATH.write_text(json.dumps({"step": STEP_DEG, "cells": cells}, separators=(",", ":")), encoding="utf-8")
    print(f"{GRID_PATH}: {len(cells)} celdas, {GRID_PATH.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
