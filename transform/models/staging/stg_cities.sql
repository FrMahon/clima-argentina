select
    city_id,
    city_name,
    province,
    region,
    latitude,
    longitude
from {{ ref('cities') }}
