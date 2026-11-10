{#
  MR builds (ADR 0009): every MR pipeline builds the whole project into the one shared
  schema set `<product>__mr__<layer>` in the team catalog (target `mr` in
  deploy/profiles.yml). Each build first drops that set, so tables left over from
  another branch can't hide a missing model.

  dbt run-operation drop_mr_environment --args '{dry_run: false}' --profiles-dir deploy --target mr
  (`dbtp mr-build` runs it). `schemas` replaces the catalog listing; it exists for tests.
#}
{% macro mr_environment_schema() %}
    {%- set environment = project_name | lower ~ '__mr' -%}
    {%- if target.name != 'mr' or target.schema | lower != environment -%}
        {{ exceptions.raise_compiler_error(
            "drop_mr_environment only runs in target 'mr' with schema '" ~ environment
            ~ "', not target '" ~ target.name ~ "' with schema '" ~ target.schema ~ "'."
        ) }}
    {%- endif -%}
    {{- return(environment) -}}
{% endmacro %}


{% macro drop_mr_environment(dry_run=true, schemas=none) %}
    {%- if execute -%}
        {%- do dbt_platform.drop_environment_schemas(dbt_platform.mr_environment_schema(), dry_run, schemas) -%}
    {%- endif -%}
{% endmacro %}
