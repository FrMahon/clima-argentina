{#
    Por defecto dbt antepone el schema del target (main_staging, main_marts…).
    Acá usamos el nombre del schema tal cual: staging, intermediate, marts, seeds.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
