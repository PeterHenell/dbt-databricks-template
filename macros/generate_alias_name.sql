{#
  Versioned models keep their plain name (`v1.customers`, not `customers_v1`); the
  version is in the schema instead (see generate_schema_name). Otherwise as dbt's default.
#}
{% macro generate_alias_name(custom_alias_name=none, node=none) -%}
    {%- if custom_alias_name -%}
        {{ custom_alias_name | trim }}
    {%- else -%}
        {{ node.name }}
    {%- endif -%}
{%- endmacro %}
