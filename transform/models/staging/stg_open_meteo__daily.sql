with source as (

    select * from {{ source('open_meteo', 'open_meteo_daily') }}

)

select
    city_id,
    date                    as weather_date,
    temperature_2m_mean     as temp_mean_c,
    temperature_2m_max      as temp_max_c,
    temperature_2m_min      as temp_min_c,
    precipitation_sum       as precipitation_mm,
    grid_latitude,
    grid_longitude,
    grid_elevation_m,
    model                   as source_model,
    extracted_at
from source
where temperature_2m_mean is not null
