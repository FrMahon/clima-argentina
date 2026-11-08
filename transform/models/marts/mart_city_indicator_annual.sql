-- Formato largo: una fila por ciudad, indicador y año.
-- Para cada indicador: el valor del año, su promedio 1961-1990, la diferencia y la media móvil
-- de 10 años de esa diferencia. Sumar un indicador nuevo = sumar un bloque al UNION.
--
-- Estaciones (hemisferio sur, trimestres meteorológicos):
--   verano   = diciembre del año anterior + enero + febrero (el verano 2024 empieza en dic-2023)
--   invierno = junio + julio + agosto

with annual as (

    select * from {{ ref('mart_city_annual') }}

),

daily as (

    select
        city_id,
        season,
        case when month = 12 then year + 1 else year end as season_year,
        temp_mean_c
    from {{ ref('fct_daily_weather') }}
    where season in ('verano', 'invierno')

),

seasons as (

    select
        city_id,
        season,
        season_year       as year,
        count(*)          as n_days,
        avg(temp_mean_c)  as temp_mean_c
    from daily
    group by city_id, season, season_year

),

-- Solo estaciones completas: verano 90 o 91 días (febrero bisiesto), invierno 92.
complete_seasons as (

    select *
    from seasons
    where (season = 'verano' and n_days >= 90)
       or (season = 'invierno' and n_days = 92)

),

last_year as (

    select max(year) as last_year from annual

),

indicators as (

    select city_id, year, 'temperatura'       as indicator, temp_mean_c      as value from annual
    union all
    select city_id, year, 'dias_calor'        as indicator, hot_days         as value from annual
    union all
    select city_id, year, 'heladas'           as indicator, frost_days       as value from annual
    union all
    select city_id, year, 'noches_tropicales' as indicator, tropical_nights  as value from annual
    union all
    select city_id, year, season              as indicator, temp_mean_c      as value
    from complete_seasons
    -- mismo rango de años que el resto de los indicadores
    where year <= (select last_year from last_year)

),

baseline as (

    select
        city_id,
        indicator,
        avg(value) as baseline_value
    from indicators
    where year between {{ var('baseline_start_year') }} and {{ var('baseline_end_year') }}
    group by city_id, indicator

),

with_change as (

    select
        indicators.city_id,
        indicators.indicator,
        indicators.year,
        indicators.value,
        baseline.baseline_value,
        indicators.value - baseline.baseline_value as change
    from indicators
    inner join baseline using (city_id, indicator)

)

select
    city_id,
    indicator,
    year,
    value,
    baseline_value,
    change,
    case
        when count(*) over last_10_years = 10
            then avg(change) over last_10_years
    end as change_10y_rolling
from with_change
window last_10_years as (
    partition by city_id, indicator
    order by year
    rows between 9 preceding and current row
)
