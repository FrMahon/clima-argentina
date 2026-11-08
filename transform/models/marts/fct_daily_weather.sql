{#
    Tabla de hechos diaria, incremental.
    En cada corrida solo procesa las filas extraídas después de la última carga
    (watermark por extracted_at). Eso cubre tres casos sin full refresh:
      - días nuevos,
      - días preliminares de ERA5 que se volvieron a descargar corregidos,
      - una ciudad nueva agregada al seed (todo su backfill tiene extracted_at nuevo).
#}
{{
    config(
        materialized='incremental',
        unique_key=['city_id', 'weather_date'],
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

select
    city_id,
    weather_date,
    year,
    month,
    decade,
    season,
    temp_mean_c,
    temp_max_c,
    temp_min_c,
    precipitation_mm,
    is_hot_day,
    is_tropical_night,
    is_frost_day,
    extracted_at
from {{ ref('int_weather_daily_enriched') }}

{% if is_incremental() %}
where extracted_at > (select max(extracted_at) from {{ this }})
{% endif %}
