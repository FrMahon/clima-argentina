-- ¿Qué meses se calentaron más? Promedio mensual del período de referencia vs. los últimos N años.

with daily as (

    select * from {{ ref('fct_daily_weather') }}

),

-- Mismo período reciente que mart_city_warming (años completos).
period as (

    select distinct recent_start_year, recent_end_year
    from {{ ref('mart_city_warming') }}

),

flagged as (

    select
        daily.city_id,
        daily.month,
        daily.temp_mean_c,
        daily.temp_max_c,
        daily.temp_min_c,
        daily.year between {{ var('baseline_start_year') }} and {{ var('baseline_end_year') }} as is_baseline,
        daily.year between period.recent_start_year and period.recent_end_year             as is_recent
    from daily
    cross join period

)

select
    flagged.city_id,
    dim_city.city_name,
    dim_city.region,
    dim_city.north_to_south_rank,
    flagged.month,
    avg(temp_mean_c) filter (where is_baseline)  as baseline_temp_mean_c,
    avg(temp_mean_c) filter (where is_recent)    as recent_temp_mean_c,
    avg(temp_mean_c) filter (where is_recent) - avg(temp_mean_c) filter (where is_baseline) as change_c,
    avg(temp_max_c)  filter (where is_recent) - avg(temp_max_c)  filter (where is_baseline) as change_max_c,
    avg(temp_min_c)  filter (where is_recent) - avg(temp_min_c)  filter (where is_baseline) as change_min_c
from flagged
inner join {{ ref('dim_city') }} as dim_city using (city_id)
group by flagged.city_id, dim_city.city_name, dim_city.region, dim_city.north_to_south_rank, flagged.month
