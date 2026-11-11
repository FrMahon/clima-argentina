# ¿Cuánto se calentó Argentina?

Pipeline ELT que descarga 85+ años de temperatura diaria de 27 ciudades argentinas (las 24 capitales y tres más), de Jujuy a
Ushuaia, la modela con **dbt** sobre **DuckDB** y publica un dashboard estático que se actualiza
solo con **GitHub Actions**.

> **Dashboard:** https://frmahon.github.io/clima-argentina/

<!-- Captura del dashboard: docs/dashboard.png -->

## Qué responde

- ¿Cuánto más cálidos son los últimos 10 años que el período de referencia 1961–1990?
- ¿Qué zonas se calentaron más: el norte, Cuyo, la Pampa o la Patagonia?
- ¿Se calentaron más los días o las noches?
- ¿Qué meses cambiaron más?
- ¿Cuántos días de calor (≥ 30 °C) y cuántas heladas hay hoy comparado con antes?

## El dashboard

Una sola página que se lee como una nota, de arriba hacia abajo:

- **La respuesta primero:** un titular que dice cuánto se calentó el país, y debajo las
  *franjas de calentamiento* de 1940 a hoy (una franja por año, azul más frío y rojo más cálido).
- **Ciudad por ciudad:** mapa y lista de las 27 ciudades, con un selector de qué ver:
  *Temperatura, Verano, Invierno, Días de calor, Heladas, Noches cálidas*. Mapa, lista, escala y
  ficha cambian juntos, y el rojo siempre significa "cambio hacia más calor" (en Heladas, rojo es
  *menos* heladas). Al tocar una ciudad se abre su ficha con los seis indicadores y sus franjas.
  El botón ▶ recorre la evolución desde 1949.
- **Mapa de calor:** un botón cambia los puntos por una capa que pinta todo el territorio. El valor
  de cada celda (grilla de 0,5°) se estima por distancia inversa al cuadrado (IDW) a partir de las
  ciudades, y la capa se recorta al contorno del país. La página aclara que es una estimación.
  Qué celdas caen dentro del país se calcula una sola vez (`python -m clima.heatgrid` →
  `dashboard/heat-grid.json`): hacerlo en el navegador congelaba la página ~2,5 s.
- **Todo conectado:** el hover en el mapa resalta la ciudad en la lista y viceversa; al pasar el
  cursor por las franjas, el mapa muestra ese año.
- **Lo que muestran los datos:** cinco hallazgos en una frase cada uno, calculados de los datos.
- La tabla completa queda en un desplegable.

El único color de la página es el de la temperatura. Funciona en modo claro y oscuro y en celular.
La vista queda en la URL para compartirla o enlazarla: `#ver=heladas`, `#ciudad=ushuaia`,
`#anio=1980`, `#tema=dark`.

## Arquitectura

```
 Open-Meteo API            data/raw/*.json             DuckDB                         site/
 (reanálisis ERA5)  ──►    respuesta cruda      ──►    raw.open_meteo_daily   ──►     data.json
                           + metadatos                       │                        + dashboard
   extract.py              (inmutable)          load.py      ▼                        (Observable Plot)
   · tramos por década                          · UNNEST     dbt
   · reintentos/backoff                         · upsert     staging → intermediate → marts
   · reanudable                                 · load_log   · fct incremental
                                                             · anomalías, tendencias, extremos
                                                             · tests de calidad

                    GitHub Actions (lun y jue): test → run → GitHub Pages
```

| Capa | Qué hace | Dónde |
|---|---|---|
| **Extract** | Pide a la API por ciudad y por década. Reintenta errores 5xx con backoff exponencial, espera cuando la API corta por minuto y se detiene limpio si corta por día. Guarda cada respuesta tal cual, dentro de un "sobre" con metadatos (qué se pidió, cuándo). | `src/clima/extract.py` |
| **Load** | DuckDB lee el JSON y lo "desarma" con `UNNEST` (listas paralelas → una fila por día). Upsert por `(city_id, date)`: si un día llega dos veces, gana la extracción más reciente. `raw.load_log` hace la carga idempotente. | `src/clima/warehouse.py` |
| **Transform** | dbt en tres capas. `fct_daily_weather` es **incremental** con watermark sobre `extracted_at`, así que también toma correcciones y ciudades nuevas sin full refresh. | `transform/models/` |
| **Calidad** | Tests de dbt en cada capa (ver abajo) y frescura de la fuente. 18 tests unitarios de Python con pytest. | `transform/tests/`, `tests/` |
| **Serve** | Exporta los marts a un JSON compacto (columnar) y arma un sitio estático. | `src/clima/export.py`, `dashboard/` |
| **Mapa** | Límites provinciales de Natural Earth (dominio público), con el contorno en su versión argentina (incluye Islas Malvinas), simplificados con Douglas-Peucker a ~50 KB. Se genera una sola vez y queda versionado. | `scripts/build_map.py`, `dashboard/argentina.geojson` |

### Modelo de datos

```
seeds/cities ─► stg_cities ─────────────┐
                                        ├─► int_weather_daily_enriched ─► fct_daily_weather (incremental)
raw.open_meteo_daily ─► stg_open_meteo__daily ┘                               │
                                                                              ├─► mart_city_annual ─► mart_city_warming
                                                    dim_city ◄────────────────┤          │                 │
                                                                              │          ▼                 ▼
                                                                              │   mart_region_annual   mart_city_monthly_change
```

| Mart | Grano | Para qué |
|---|---|---|
| `dim_city` | ciudad | Coordenadas, celda ERA5 que la representa, cobertura de datos |
| `fct_daily_weather` | ciudad × día | Hechos diarios + banderas de día de calor, noche tropical, helada |
| `mart_city_annual` | ciudad × año | Promedios, extremos, anomalía vs. 1961–1990 y media móvil de 10 años |
| `mart_city_warming` | ciudad | Calentamiento reciente vs. referencia, tendencia lineal (°C/década), días extremos |
| `mart_region_annual` | región × año | Anomalía por región y para el país |
| `mart_city_monthly_change` | ciudad × mes | Qué meses se calentaron más |
| `mart_city_indicator_annual` | ciudad × indicador × año | Formato largo para el dashboard: temperatura anual, verano (DJF), invierno (JJA), días de calor, heladas y noches tropicales, con su referencia 1961–1990 y media móvil. Un indicador nuevo es un bloque más en el `UNION`, no una columna nueva |

### Tests de calidad

- **Integridad:** claves únicas compuestas (`city_id` + fecha/año/mes), `not_null`, relaciones hacia `dim_city`.
- **Rangos físicos:** temperaturas y precipitación dentro de valores posibles; anomalías en ±5 °C.
- **Coherencia:** mínima ≤ media ≤ máxima en cada día.
- **Completitud:** ninguna ciudad tiene días faltantes entre su primer y último dato.
- **Frescura:** alerta si el último dato tiene más de 16 días y error a los 30.
- **Python:** planificación de tramos, reanudación, reintentos y límites de la API, idempotencia de la carga, que el archivo más nuevo gane en días solapados.

## Cómo correrlo

Requiere Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

clima run          # extract → load → transform → export
```

O etapa por etapa:

```bash
clima extract      # descarga lo pendiente (la primera vez, el backfill completo desde 1940)
clima load         # carga los JSON nuevos en DuckDB
clima transform    # dbt source freshness + dbt build (seeds, modelos y tests)
clima export       # genera site/
pytest             # tests de Python
```

Para ver el dashboard en local:

```bash
python -m http.server -d site 8000   # → http://localhost:8000
```

Para explorar los datos con SQL:

```bash
duckdb data/warehouse.duckdb "select city_name, round(warming_c, 2) as warming_c from marts.mart_city_warming order by 2 desc"
```

La primera corrida tarda unos 20 minutos: la API gratuita limita los pedidos por minuto y el
extractor espera solo. Si se llega al límite diario, lo descargado queda guardado y la próxima
corrida sigue desde ahí.

## Publicarlo con GitHub Pages

1. Subí el repo a GitHub.
2. En **Settings → Pages**, elegí **Source: GitHub Actions**.
3. Corré el workflow **pipeline** desde la pestaña **Actions** (o esperá al lunes).

El estado entre corridas (JSON crudos + warehouse) se guarda en la caché de Actions. Si la caché
expira, el pipeline rehace el backfill solo, porque cada etapa es idempotente.

La primera corrida descarga todo el histórico y puede chocar con la cuota horaria de la API: en ese
caso termina con error, pero lo descargado queda en la caché y la siguiente corrida (una hora
después) sigue desde ahí. Una vez completo el histórico, si la API corta en una corrida programada,
el pipeline publica igual con los datos que ya tiene en vez de fallar.

## Decisiones de diseño

- **ERA5 puro (`models=era5`) y no `best_match`.** Para una tendencia de 85 años importa que toda
  la serie venga del mismo modelo. Mezclar fuentes de distinta resolución podría crear un "salto"
  artificial.
- **Período de referencia 1961–1990.** Es el estándar de la OMM para estudiar el cambio climático.
- **Tendencia principal desde 1980.** Antes de la era satelital, ERA5 tiene menos observaciones
  (sobre todo antes de 1950), así que esos años son más inciertos.
- **Solo años completos.** Un año a medias sesga el promedio (le falta el verano o el invierno).
- **Ventana de refresco de 90 días.** Los últimos meses de ERA5 son preliminares (ERA5T) y se
  corrigen; cada corrida incremental los vuelve a pedir y el upsert reemplaza los valores.
- **DuckDB + dashboard estático.** Todo corre gratis: sin servidores ni base de datos en la nube.

## Limitaciones

- ERA5 es un reanálisis en una grilla de ~25 km, no el dato de una estación. En zonas de montaña
  o costa la celda puede diferir del valor local.
- El promedio "nacional" es un promedio simple de 27 ciudades (cada una pesa igual), no un promedio
  areal del territorio. Como hay una capital por provincia, las provincias chicas y densas del
  centro y el litoral pesan más que su superficie, y la Patagonia pesa menos.

## Stack

Python · requests · DuckDB · dbt-core + dbt-duckdb · pytest · GitHub Actions · GitHub Pages ·
Observable Plot · Natural Earth

Datos: [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api),
reanálisis ERA5 de ECMWF / Copernicus (CC BY 4.0).
