-- Coherencia física: mínima ≤ media ≤ máxima.
-- Tolerancia de 0.1 °C porque la API redondea cada valor a un decimal.
select *
from {{ ref('fct_daily_weather') }}
where temp_min_c  > temp_mean_c + 0.1
   or temp_mean_c > temp_max_c  + 0.1
