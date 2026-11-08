-- Anomalía anual promedio por región y para el país.
-- Promedio simple de las ciudades (cada ciudad pesa igual): es un indicador de la muestra,
-- no un promedio areal oficial del territorio.

with annual as (

    select * from {{ ref('mart_city_annual') }}

),

by_area as (

    select region as area, 'region' as area_type, year,
           avg(anomaly_c) as anomaly_c, count(*) as n_cities
    from annual
    group by region, year

    union all

    select 'Argentina' as area, 'country' as area_type, year,
           avg(anomaly_c) as anomaly_c, count(*) as n_cities
    from annual
    group by year

)

select
    area,
    area_type,
    year,
    n_cities,
    anomaly_c,
    case
        when count(*) over last_10_years = 10
            then avg(anomaly_c) over last_10_years
    end as anomaly_10y_rolling_c
from by_area
window last_10_years as (
    partition by area
    order by year
    rows between 9 preceding and current row
)
