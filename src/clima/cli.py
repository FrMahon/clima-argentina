"""CLI del pipeline.

    clima extract     descarga lo pendiente de la API → data/raw/
    clima load        carga los archivos crudos nuevos → DuckDB (raw.*)
    clima transform   dbt: seeds, modelos y tests (+ chequeo de frescura)
    clima export      marts → site/data.json + dashboard estático
    clima run         todo lo anterior, en orden
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

from . import config, export, extract, warehouse

log = logging.getLogger("clima")

EXIT_RATE_LIMIT = 2


def cmd_extract() -> int:
    with warehouse.connect() as con:
        watermarks = warehouse.get_watermarks(con)
    try:
        extract.run(watermarks)
    except extract.RateLimitExceeded as exc:
        log.warning("La API cortó por cuota (%s). Lo descargado quedó guardado; volvé a correr más tarde.", exc)
        return EXIT_RATE_LIMIT
    return 0


def cmd_load() -> int:
    with warehouse.connect() as con:
        warehouse.load_raw_files(con)
    return 0


def cmd_transform() -> int:
    from dbt.cli.main import dbtRunner  # import diferido: dbt tarda en cargar

    os.environ["DUCKDB_PATH"] = str(config.DB_PATH)
    dirs = ["--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR)]
    runner = dbtRunner()
    # full-refresh del seed: si la base cacheada tiene el esquema viejo de `cities`
    # (6 columnas), dbt seed falla al leer el CSV nuevo (7 columnas).
    for args in (["source", "freshness"], ["seed", "--full-refresh"], ["build"]):
        result = runner.invoke([*args, *dirs])
        if not result.success:
            log.error("dbt %s falló", " ".join(args))
            return 1
    return 0


def cmd_export() -> int:
    export.run()
    return 0


def cmd_run() -> int:
    # Los push (cambios de código/dashboard) republican con los datos cacheados, sin gastar cuota de la API.
    code = 0 if os.environ.get("CLIMA_SKIP_EXTRACT") else cmd_extract()
    cmd_load()  # se carga lo que haya llegado, aunque la extracción se haya cortado
    if code != 0:
        with warehouse.connect() as con:
            watermarks = warehouse.get_watermarks(con)
        if not extract.history_complete(extract.read_cities(), watermarks, date.today()):
            log.warning("Falta parte del histórico: no se transforma con datos parciales.")
            return code
        log.warning("La API cortó, pero el histórico está completo: se publica con los datos que hay.")
    return cmd_transform() or cmd_export()


COMMANDS = {
    "extract": cmd_extract,
    "load": cmd_load,
    "transform": cmd_transform,
    "export": cmd_export,
    "run": cmd_run,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clima", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return COMMANDS[args.command]()


if __name__ == "__main__":
    sys.exit(main())
