-- Resumen por ciudad: ¿cuánto se calentó?
-- Compara el período de referencia (1961-1990) con los últimos N años completos
-- y calcula la tendencia lineal (°C por década).

with annual as (

    select * from {{ ref('mart_city_annual') }}

),

-- Último año completo común a todas las ciudades, para comparar el mismo período.
period as (

    select min(last_year) as recent_end_year
    from (select city_id, max(year) as last_year from annual group by city_id)

),

flagged as (

    select
        annual.*,
        year between {{ var('baseline_start_year') }} and {{ var('baseline_end_year') }} as is_baseline,
        year between period.recent_end_year - {{ var('recent_years') }} + 1
                 and period.recent_end_year                                           as is_recent,
        period.recent_end_year
    from annual
    cross join period

),

summary as (

    select
        city_id,
        any_value(recent_end_year) - {{ var('recent_years') }} + 1     as recent_start_year,
        any_value(recent_end_year)                                     as recent_end_year,

        avg(temp_mean_c)    filter (where is_baseline)  as baseline_temp_mean_c,
        avg(temp_mean_c)    filter (where is_recent)    as recent_temp_mean_c,
        avg(temp_max_avg_c) filter (where is_baseline)  as baseline_temp_max_avg_c,
        avg(temp_max_avg_c) filter (where is_recent)    as recent_temp_max_avg_c,
        avg(temp_min_avg_c) filter (where is_baseline)  as baseline_temp_min_avg_c,
        avg(temp_min_avg_c) filter (where is_recent)    as recent_temp_min_avg_c,

        avg(hot_days)        filter (where is_baseline) as baseline_hot_days,
        avg(hot_days)        filter (where is_recent)   as recent_hot_days,
        avg(tropical_nights) filter (where is_baseline) as baseline_tropical_nights,
        avg(tropical_nights) filter (where is_recent)   as recent_tropical_nights,
        avg(frost_days)      filter (where is_baseline) as baseline_frost_days,
        avg(frost_days)      filter (where is_recent)   as recent_frost_days,

        -- Pendiente de la regresión lineal temperatura ~ año, pasada a °C por década.
        regr_slope(temp_mean_c, year) * 10                               as trend_c_per_decade_since_1940,
        regr_slope(temp_mean_c, year) filter (where year >= 1980) * 10   as trend_c_per_decade_since_1980,
        regr_r2(temp_mean_c, year)    filter (where year >= 1980)        as trend_r2_since_1980,

        arg_max(year, temp_mean_c)  as warmest_year,
        max(temp_mean_c)            as warmest_year_temp_mean_c,
        min(year)                   as first_year,
        max(year)                   as last_year
    from flagged
    group by city_id

)

select
    summary.city_id,
    dim_city.city_name,
    dim_city.province,
    dim_city.region,
    dim_city.latitude,
    dim_city.north_to_south_rank,
    summary.recent_start_year,
    summary.recent_end_year,
    summary.baseline_temp_mean_c,
    summary.recent_temp_mean_c,
    summary.recent_temp_mean_c     - summary.baseline_temp_mean_c     as warming_c,
    summary.recent_temp_max_avg_c  - summary.baseline_temp_max_avg_c  as warming_max_c,
    summary.recent_temp_min_avg_c  - summary.baseline_temp_min_avg_c  as warming_min_c,
    summary.baseline_hot_days,
    summary.recent_hot_days,
    summary.baseline_tropical_nights,
    summary.recent_tropical_nights,
    summary.baseline_frost_days,
    summary.recent_frost_days,
    summary.trend_c_per_decade_since_1940,
    summary.trend_c_per_decade_since_1980,
    summary.trend_r2_since_1980,
    summary.warmest_year,
    summary.warmest_year_temp_mean_c,
    summary.first_year,
    summary.last_year
from summary
inner join {{ ref('dim_city') }} as dim_city using (city_id)
