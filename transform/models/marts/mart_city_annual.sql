-- Una fila por ciudad y año completo, con la anomalía respecto al período de referencia.

with daily as (

    select * from {{ ref('fct_daily_weather') }}

),

annual as (

    select
        city_id,
        year,
        count(*)                       as n_days,
        avg(temp_mean_c)               as temp_mean_c,
        avg(temp_max_c)                as temp_max_avg_c,
        avg(temp_min_c)                as temp_min_avg_c,
        max(temp_max_c)                as temp_max_abs_c,
        min(temp_min_c)                as temp_min_abs_c,
        count_if(is_hot_day)           as hot_days,
        count_if(is_tropical_night)    as tropical_nights,
        count_if(is_frost_day)         as frost_days,
        sum(precipitation_mm)          as precipitation_mm
    from daily
    group by city_id, year

),

-- Solo años con todos sus días: un año a medias sesgaría el promedio (falta el verano o el invierno).
complete_years as (

    select *
    from annual
    where n_days = date_diff('day', make_date(year, 1, 1), make_date(year + 1, 1, 1))

),

baseline as (

    select
        city_id,
        avg(temp_mean_c) as baseline_temp_mean_c
    from complete_years
    where year between {{ var('baseline_start_year') }} and {{ var('baseline_end_year') }}
    group by city_id

),

with_anomaly as (

    select
        complete_years.*,
        baseline.baseline_temp_mean_c,
        complete_years.temp_mean_c - baseline.baseline_temp_mean_c as anomaly_c
    from complete_years
    inner join baseline using (city_id)

)

select
    with_anomaly.city_id,
    dim_city.city_name,
    dim_city.region,
    with_anomaly.year,
    with_anomaly.n_days,
    with_anomaly.temp_mean_c,
    with_anomaly.temp_max_avg_c,
    with_anomaly.temp_min_avg_c,
    with_anomaly.temp_max_abs_c,
    with_anomaly.temp_min_abs_c,
    with_anomaly.hot_days,
    with_anomaly.tropical_nights,
    with_anomaly.frost_days,
    with_anomaly.precipitation_mm,
    with_anomaly.baseline_temp_mean_c,
    with_anomaly.anomaly_c,
    -- Media móvil de 10 años: solo cuando hay 10 años completos en la ventana.
    case
        when count(*) over last_10_years = 10
            then avg(with_anomaly.anomaly_c) over last_10_years
    end as anomaly_10y_rolling_c
from with_anomaly
inner join {{ ref('dim_city') }} as dim_city using (city_id)
window last_10_years as (
    partition by with_anomaly.city_id
    order by with_anomaly.year
    rows between 9 preceding and current row
)
