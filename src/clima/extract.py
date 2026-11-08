"""Extracción: Open-Meteo Historical Weather API (reanálisis ERA5) → archivos JSON crudos.

Cada pedido cubre una ciudad y como máximo una década, y se guarda tal cual vino de la API
dentro de un "sobre" con metadatos (qué se pidió y cuándo). Así la capa cruda es inmutable,
se puede reprocesar sin volver a llamar a la API y una descarga cortada se puede reanudar.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import requests

from . import config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class City:
    city_id: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Chunk:
    city: City
    start: date
    end: date

    @property
    def prefix(self) -> str:
        return f"{self.city.city_id}__{self.start:%Y%m%d}__{self.end:%Y%m%d}"


class RateLimitExceeded(RuntimeError):
    """La API cortó por cuota (hora/día). El progreso queda guardado; hay que reintentar más tarde."""


def read_cities(path: Path = config.CITIES_CSV) -> list[City]:
    with open(path, encoding="utf-8", newline="") as f:
        return [
            City(r["city_id"], r["city_name"], float(r["latitude"]), float(r["longitude"]))
            for r in csv.DictReader(f)
        ]


# --- Planificación ------------------------------------------------------------

def plan_chunks(city: City, start: date, end: date, years: int = config.CHUNK_YEARS) -> list[Chunk]:
    """Parte [start, end] en tramos alineados a décadas calendario (1940-1949, 1950-1959, …)."""
    chunks: list[Chunk] = []
    current = start
    while current <= end:
        block_end = date((current.year // years) * years + years - 1, 12, 31)
        chunk_end = min(block_end, end)
        chunks.append(Chunk(city, current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _already_extracted(chunk: Chunk, raw_dir: Path) -> bool:
    return any((raw_dir / chunk.city.city_id).glob(f"{chunk.prefix}__*.json"))


def plan_extraction(
    cities: Iterable[City],
    watermarks: dict[str, date],
    today: date,
    raw_dir: Path = config.RAW_DIR,
) -> list[Chunk]:
    """Decide qué descargar.

    - Ciudad sin datos cargados → backfill completo desde 1940.
    - Ciudad con datos → desde (último día cargado − ventana de refresco), porque ERA5 corrige
      sus datos preliminares durante unos meses.
    - Un tramo "cerrado" (que terminó antes de la ventana de refresco) que ya está en disco no se
      vuelve a pedir: eso permite reanudar un backfill cortado sin repetir pedidos.
    """
    end = today - timedelta(days=config.ERA5_LAG_DAYS)
    refresh = timedelta(days=config.REFRESH_WINDOW_DAYS)
    plan: list[Chunk] = []
    for city in cities:
        watermark = watermarks.get(city.city_id)
        start = max(config.START_DATE, watermark - refresh) if watermark else config.START_DATE
        for chunk in plan_chunks(city, start, end):
            closed = chunk.end <= end - refresh
            if closed and _already_extracted(chunk, raw_dir):
                continue
            plan.append(chunk)
    return plan


def history_complete(cities: Iterable[City], watermarks: dict[str, date], today: date) -> bool:
    """¿Todas las ciudades tienen el histórico cargado hasta hace poco?

    Si es así y la API corta por cuota, se puede transformar y publicar igual: los datos quedan
    a lo sumo unos días atrasados. Si alguna ciudad no tiene datos o quedó a mitad del backfill,
    no (los tests de completitud fallarían y el dashboard mostraría huecos).
    """
    recent_enough = today - timedelta(days=config.ERA5_LAG_DAYS + config.REFRESH_WINDOW_DAYS)
    return all(watermarks.get(c.city_id) and watermarks[c.city_id] >= recent_enough for c in cities)


# --- Cliente HTTP -------------------------------------------------------------

class OpenMeteoClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.sleep = sleep

    @staticmethod
    def params_for(chunk: Chunk) -> dict[str, str | float]:
        return {
            "latitude": chunk.city.latitude,
            "longitude": chunk.city.longitude,
            "start_date": chunk.start.isoformat(),
            "end_date": chunk.end.isoformat(),
            "daily": ",".join(config.DAILY_VARIABLES),
            "timezone": config.TIMEZONE,
            "models": config.MODEL,
        }

    def fetch(self, chunk: Chunk) -> dict:
        params = self.params_for(chunk)
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(config.API_URL, params=params, timeout=120)
            except requests.RequestException as exc:  # red caída, timeout, etc.
                last_error = repr(exc)
                self._backoff(attempt, last_error)
                continue

            if resp.status_code == 200:
                return resp.json()

            reason = _reason(resp)
            last_error = f"HTTP {resp.status_code}: {reason}"
            if resp.status_code == 429:
                if "minut" in reason.lower():
                    log.warning("Límite por minuto alcanzado; espero 60 s…")
                    self.sleep(60)
                    continue
                raise RateLimitExceeded(reason or "Límite de la API alcanzado")
            if resp.status_code >= 500:
                self._backoff(attempt, last_error)
                continue
            raise RuntimeError(f"Pedido rechazado por la API ({chunk.prefix}): {last_error}")

        raise RuntimeError(f"Falló {chunk.prefix} tras {self.max_retries} intentos: {last_error}")

    def _backoff(self, attempt: int, error: str) -> None:
        wait = min(2**attempt, 60)
        log.warning("Intento %d falló (%s); reintento en %d s", attempt, error, wait)
        self.sleep(wait)


def _reason(resp) -> str:
    try:
        return str(resp.json().get("reason", ""))
    except Exception:  # noqa: BLE001 — cuerpo no JSON
        return ""


# --- Persistencia cruda ---------------------------------------------------------

def write_raw(chunk: Chunk, payload: dict, raw_dir: Path = config.RAW_DIR) -> Path:
    """Guarda la respuesta en un sobre con metadatos. Escritura atómica (tmp + rename)."""
    extracted_at = datetime.now(timezone.utc)
    envelope = {
        "city_id": chunk.city.city_id,
        "requested_start": chunk.start.isoformat(),
        "requested_end": chunk.end.isoformat(),
        "extracted_at": extracted_at.isoformat(),
        "source": config.API_URL,
        "model": config.MODEL,
        "response": payload,
    }
    city_dir = raw_dir / chunk.city.city_id
    city_dir.mkdir(parents=True, exist_ok=True)
    path = city_dir / f"{chunk.prefix}__{extracted_at:%Y%m%dT%H%M%S}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope), encoding="utf-8")
    tmp.replace(path)
    return path


def run(
    watermarks: dict[str, date],
    today: date | None = None,
    client: OpenMeteoClient | None = None,
    raw_dir: Path = config.RAW_DIR,
) -> list[Path]:
    """Descarga todo lo pendiente. Si la API corta por cuota, lanza RateLimitExceeded
    (lo descargado hasta ese momento ya quedó guardado)."""
    today = today or date.today()
    client = client or OpenMeteoClient()
    chunks = plan_extraction(read_cities(), watermarks, today, raw_dir)
    log.info("Extracción: %d tramos pendientes", len(chunks))

    written: list[Path] = []
    for i, chunk in enumerate(chunks, 1):
        payload = client.fetch(chunk)
        written.append(write_raw(chunk, payload, raw_dir))
        n_days = len(payload.get("daily", {}).get("time", []))
        log.info("[%d/%d] %s %s → %s (%d días)", i, len(chunks), chunk.city.city_id, chunk.start, chunk.end, n_days)
        if i < len(chunks):
            time.sleep(config.REQUEST_PAUSE_S)
    return written
