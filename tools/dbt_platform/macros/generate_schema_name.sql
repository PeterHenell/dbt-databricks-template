{#
  One schema per layer: staging, intermediate, published, seeds.

  - Deployment target `prod` (deploy/profiles.yml, used for product dev and product prod):
      plain `<layer>` in the product catalog.
  - Every other target (personal dev, MR builds): `<target.schema>__<layer>` in the team catalog.
    target.schema is `<product>__<alias>` for a developer, so they get
    `<product>__<alias>__<layer>` (ADR 0001).

  Nodes without a layer fall back to target.schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set layer = custom_schema_name | trim if custom_schema_name is not none else '' -%}
    {%- if not layer -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ layer }}
    {%- else -%}
        {{ target.schema }}__{{ layer }}
    {%- endif -%}
{%- endmacro %}
