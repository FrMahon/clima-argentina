"""Configuración central del pipeline. Las rutas se pueden sobreescribir con variables de entorno."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("CLIMA_DATA_DIR", ROOT_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.environ.get("DUCKDB_PATH", DATA_DIR / "warehouse.duckdb"))

DBT_DIR = ROOT_DIR / "transform"
CITIES_CSV = DBT_DIR / "seeds" / "cities.csv"
DASHBOARD_DIR = ROOT_DIR / "dashboard"
SITE_DIR = ROOT_DIR / "site"

# --- Fuente: Open-Meteo Historical Weather API ---------------------------------
API_URL = "https://archive-api.open-meteo.com/v1/archive"
# ERA5 puro (no "best_match"): mismo modelo para toda la serie 1940→hoy,
# así la tendencia de largo plazo no mezcla fuentes con distinta resolución.
MODEL = "era5"
TIMEZONE = "America/Argentina/Buenos_Aires"
DAILY_VARIABLES = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
)

START_DATE = date(1940, 1, 1)
# ERA5 se publica con ~5 días de demora; pedimos hasta hace 7 para no recibir días vacíos.
ERA5_LAG_DAYS = 7
# Los últimos meses de ERA5 son preliminares (ERA5T) y pueden corregirse:
# en cada corrida incremental se vuelve a descargar esta ventana.
REFRESH_WINDOW_DAYS = 90
# Tamaño de cada pedido a la API: una década por archivo, para poder reanudar.
CHUNK_YEARS = 10
# Pausa de cortesía entre pedidos (segundos).
REQUEST_PAUSE_S = 1.0
