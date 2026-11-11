select
    city_id,
    city_name,
    province,
    region,
    is_capital,
    latitude,
    longitude
from {{ ref('cities') }}
