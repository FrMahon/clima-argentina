-- Agrega a cada día la ciudad, atributos de calendario y las banderas de días extremos.

with weather as (

    select * from {{ ref('stg_open_meteo__daily') }}

),

cities as (

    select * from {{ ref('stg_cities') }}

)

select
    weather.city_id,
    cities.city_name,
    cities.region,
    weather.weather_date,
    year(weather.weather_date)                         as year,
    month(weather.weather_date)                        as month,
    (year(weather.weather_date) // 10) * 10            as decade,
    -- Estaciones del hemisferio sur por trimestre meteorológico.
    case
        when month(weather.weather_date) in (12, 1, 2) then 'verano'
        when month(weather.weather_date) in (3, 4, 5)  then 'otoño'
        when month(weather.weather_date) in (6, 7, 8)  then 'invierno'
        else 'primavera'
    end                                                as season,
    weather.temp_mean_c,
    weather.temp_max_c,
    weather.temp_min_c,
    weather.precipitation_mm,
    weather.temp_max_c >= {{ var('hot_day_threshold_c') }}        as is_hot_day,
    weather.temp_min_c >= {{ var('tropical_night_threshold_c') }} as is_tropical_night,
    weather.temp_min_c <  {{ var('frost_threshold_c') }}          as is_frost_day,
    weather.extracted_at
from weather
inner join cities using (city_id)
