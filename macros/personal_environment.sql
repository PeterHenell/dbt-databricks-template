{#
  The developer's personal environment: every schema in the team catalog named
  `<product>__<alias>__*` (ADR 0001), plus the bare `<product>__<alias>`.
  target.schema in the dev profile is `<product>__<alias>`.
#}

{% macro personal_environment_schema() %}
    {#- target.schema, after checking it is a personal environment (never prod, never MR). -#}
    {%- set environment = target.schema | lower -%}
    {%- set product_prefix = project_name | lower ~ '__' -%}
    {%- set alias = environment[product_prefix | length:] -%}
    {%- if target.name == 'prod' -%}
        {{ exceptions.raise_compiler_error("Refusing to touch the personal environment in target 'prod'.") }}
    {%- endif -%}
    {%- if not environment.startswith(product_prefix) or not alias or '__' in alias
          or alias.startswith('_') or alias.endswith('_') -%}
        {{ exceptions.raise_compiler_error(
            "target.schema '" ~ target.schema ~ "' is not a personal environment ('"
            ~ product_prefix ~ "<alias>'). Check `schema` in profiles.yml or run `make setup`."
        ) }}
    {%- endif -%}
    {%- if alias == 'mr' -%}
        {{ exceptions.raise_compiler_error("Alias 'mr' is reserved for MR builds (ADR 0009); choose another in profiles.yml.") }}
    {%- endif -%}
    {{- return(environment) -}}
{% endmacro %}


{% macro select_personal_schemas(schemas, environment) %}
    {#- The schemas in `schemas` that belong to `environment` (`<product>__<alias>`). -#}
    {#- The trailing `__` keeps `orders__pe__` from matching `orders__pehe__staging`. -#}
    {%- set prefix = environment ~ '__' -%}
    {%- set selected = [] -%}
    {%- for schema in schemas -%}
        {%- set name = schema | lower -%}
        {%- if name == environment or name.startswith(prefix) -%}
            {%- do selected.append(name) -%}
        {%- endif -%}
    {%- endfor -%}
    {{- return(selected | sort) -}}
{% endmacro %}


{% macro list_catalog_schemas(catalog) %}
    {{- return(adapter.dispatch('list_catalog_schemas')(catalog)) -}}
{% endmacro %}

{% macro databricks__list_catalog_schemas(catalog) %}
    {%- set result = run_query('show schemas in ' ~ adapter.quote(catalog)) -%}
    {{- return(result.columns[0].values() | list) -}}
{% endmacro %}

{#- The local Spark engine (local/) has one catalog and no catalog names. -#}
{% macro spark__list_catalog_schemas(catalog) %}
    {%- set result = run_query('show schemas') -%}
    {{- return(result.columns[0].values() | list) -}}
{% endmacro %}


{#
  `make clean-dev`: dbt run-operation drop_personal_environment --args '{dry_run: false}'
  dry_run (default true) only prints what would be dropped.
  `schemas` replaces the catalog listing; it exists for tests.
#}
{% macro drop_personal_environment(dry_run=true, schemas=none) %}
    {%- if execute -%}
        {%- set environment = personal_environment_schema() -%}
        {%- set catalog = target.database -%}  {#- none on the local Spark engine -#}
        {%- set where = 'catalog ' ~ catalog if catalog else 'the local catalog' -%}
        {%- set all_schemas = schemas if schemas is not none else list_catalog_schemas(catalog) -%}
        {%- set to_drop = select_personal_schemas(all_schemas, environment) -%}

        {%- if not to_drop -%}
            {%- do print("Nothing to drop: no schemas named " ~ environment ~ "__* in " ~ where ~ ".") -%}
        {%- elif dry_run -%}
            {%- do print("Schemas in " ~ where ~ " that will be dropped (with all their tables and views):") -%}
            {%- for schema in to_drop -%}
                {%- do print("  " ~ schema) -%}
            {%- endfor -%}
        {%- else -%}
            {%- for schema in to_drop -%}
                {%- do print("Dropping " ~ schema) -%}
                {%- do adapter.drop_schema(api.Relation.create(database=catalog, schema=schema)) -%}
            {%- endfor -%}
            {%- do print("Dropped " ~ to_drop | length ~ " schema(s).") -%}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}
