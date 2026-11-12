{#
  The platform macros live in the dbt_platform package (tools/dbt_platform/, installed
  by `dbt deps` from packages.yml). dbt only takes these overrides from the root
  project, so they stay here as one-line stubs. Keep them as they are; change the
  behaviour in the package.
#}

{#- One schema per layer; personal and MR targets get `<target.schema>__<layer>`. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ return(dbt_platform.generate_schema_name(custom_schema_name, node)) }}
{%- endmacro %}

{#- Source modes: personal targets read their shallow clones by default. -#}
{% macro source(source_name, table_name) -%}
    {{ return(dbt_platform.source(source_name, table_name)) }}
{%- endmacro %}

{#- Local Spark engine: NOT NULL as a CHECK constraint. On Databricks the package hands
    the call back to dbt-databricks (see the package macro for why that is needed). -#}
{% macro spark__alter_column_set_constraints(relation, column_dict) -%}
    {{ return(dbt_platform.local_spark_alter_column_set_constraints(relation, column_dict)) }}
{%- endmacro %}
