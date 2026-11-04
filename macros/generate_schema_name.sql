{#
  One schema per layer: staging, intermediate, and one `vN` per published version.

  - Deployment target `prod` (deploy/profiles.yml, used for product dev and product prod):
      plain `<layer>` in the product catalog.
  - Every other target (personal dev, MR builds): `<target.schema>__<layer>` in the team catalog.
    target.schema is `<product>__<alias>` for a developer, so they get
    `<product>__<alias>__<layer>` (ADR 0001).

  The `published` layer is versioned (ADR 0003): version N of a model goes to layer `vN`.
  (dbt calls this macro once before a model's YAML `versions:` are applied, so an
  unversioned published model is not rejected here but by
  `assert_published_models_are_versioned`, run on run start.)
  Nodes without a layer fall back to target.schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set layer = custom_schema_name | trim if custom_schema_name is not none else '' -%}
    {%- if layer == 'published' and node.version is not none and node.version is defined -%}
        {%- set layer = 'v' ~ node.version -%}
    {%- endif -%}
    {%- if not layer -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ layer }}
    {%- else -%}
        {{ target.schema }}__{{ layer }}
    {%- endif -%}
{%- endmacro %}
