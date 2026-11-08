-- Completitud: cada ciudad tiene un día por fecha, sin huecos, entre su primer y último día.
select
    city_id,
    min(weather_date) as first_date,
    max(weather_date) as last_date,
    count(*)          as n_days,
    date_diff('day', min(weather_date), max(weather_date)) + 1 as expected_days
from {{ ref('fct_daily_weather') }}
group by city_id
having count(*) <> date_diff('day', min(weather_date), max(weather_date)) + 1
