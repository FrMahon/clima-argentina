-- Cobertura: están las 24 capitales (23 provincias + CABA), una por jurisdicción.
-- Devuelve filas si alguna provincia tiene 0 o más de 1 capital, o si no son 24 en total.
with capitals as (

    select province, count(*) as n
    from {{ ref('stg_cities') }}
    where is_capital
    group by province

)

select province, n, 'capitales por provincia distinto de 1' as problema
from capitals
where n <> 1

union all

select 'total' as province, count(*) as n, 'no hay 24 jurisdicciones con capital' as problema
from capitals
having count(*) <> 24
