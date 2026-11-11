-- Una fila por ciudad, con la celda de ERA5 que la representa y la cobertura de datos.

with cities as (

    select * from {{ ref('stg_cities') }}

),

coverage as (

    select
        city_id,
        any_value(grid_latitude)     as grid_latitude,
        any_value(grid_longitude)    as grid_longitude,
        any_value(grid_elevation_m)  as grid_elevation_m,
        min(weather_date)            as first_date,
        max(weather_date)            as last_date,
        count(*)                     as n_days
    from {{ ref('stg_open_meteo__daily') }}
    group by city_id

)

select
    cities.city_id,
    cities.city_name,
    cities.province,
    cities.region,
    cities.is_capital,
    cities.latitude,
    cities.longitude,
    coverage.grid_latitude,
    coverage.grid_longitude,
    coverage.grid_elevation_m,
    coverage.first_date,
    coverage.last_date,
    coverage.n_days,
    -- Orden geográfico norte → sur para gráficos y tablas.
    row_number() over (order by cities.latitude desc) as north_to_south_rank
from cities
left join coverage using (city_id)
