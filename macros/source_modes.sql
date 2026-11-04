{#
  Source modes (ADR 0005). `dev_source_mode` = prod | clone | sample (default clone)
  chooses where a personal environment reads its sources from:

    prod    the prod location declared in the source YAML
    clone   personal Delta shallow clones in `<product>__<alias>__src_clone`, made by
            `make clone-sources`, named `<source>__<table>`
    sample  reserved; how samples are made is not decided yet

  Only personal targets (`dev`, and `local` for the local Spark engine) use the mode.
  Every other target (prod, MR builds) always reads prod. Override per run with
  `--vars '{dev_source_mode: prod}'`.
#}

{% macro is_personal_target() %}
    {{- return(target.name in ['dev', 'local']) -}}
{% endmacro %}


{% macro dev_source_mode() %}
    {%- set mode = var('dev_source_mode', 'clone') -%}
    {%- if mode not in ['prod', 'clone', 'sample'] -%}
        {{ exceptions.raise_compiler_error("dev_source_mode must be prod, clone or sample, not '" ~ mode ~ "'.") }}
    {%- endif -%}
    {{- return(mode if is_personal_target() else 'prod') -}}
{% endmacro %}


{% macro source_clone_schema() %}
    {{- return(target.schema ~ '__src_clone') -}}
{% endmacro %}


{% macro source_clone_identifier(source_name, table_name) %}
    {{- return(source_name ~ '__' ~ table_name) -}}
{% endmacro %}


{#- Overrides dbt's source(): same lineage (builtins.source), location chosen by the mode. -#}
{% macro source(source_name, table_name) %}
    {%- set prod_relation = builtins.source(source_name, table_name) -%}
    {%- set mode = dev_source_mode() -%}
    {%- if mode == 'prod' -%}
        {{- return(prod_relation) -}}
    {%- elif mode == 'sample' -%}
        {{ exceptions.raise_compiler_error(
            "dev_source_mode 'sample' is not implemented yet. Use clone or prod, e.g. --vars '{dev_source_mode: prod}'."
        ) }}
    {%- endif -%}
    {{- return(prod_relation.incorporate(path={
        'database': target.database,
        'schema': source_clone_schema(),
        'identifier': source_clone_identifier(source_name, table_name),
    })) -}}
{% endmacro %}


{#- (Re)create `clone` as a shallow clone of `prod`. `existing` is the current clone table, if any. -#}
{% macro databricks__shallow_clone_table(clone, prod, existing) %}
    {%- do run_query('create or replace table ' ~ clone ~ ' shallow clone ' ~ prod) -%}
{% endmacro %}

{#- Local Spark engine: open-source Delta can't replace a non-empty table with a clone. -#}
{% macro spark__shallow_clone_table(clone, prod, existing) %}
    {%- if existing is not none -%}{% do adapter.drop_relation(existing) %}{%- endif -%}
    {%- do run_query('create table ' ~ clone ~ ' shallow clone ' ~ prod) -%}
{% endmacro %}


{#
  `make clone-sources`: (re)create a Delta shallow clone of every declared source table
  in `<product>__<alias>__src_clone`. Re-creating also repairs clones broken by prod
  `VACUUM`. Views can't be shallow-cloned: for those a view of the same name that reads
  the prod view is created instead, so their data always comes from prod.
#}
{% macro clone_sources() %}
    {%- if execute -%}
        {%- if not is_personal_target() -%}
            {{ exceptions.raise_compiler_error("clone_sources only runs in a personal environment, not target '" ~ target.name ~ "'.") }}
        {%- endif -%}
        {%- do personal_environment_schema() -%}  {#- refuses anything that isn't a personal environment -#}
        {%- set clone_schema = source_clone_schema() -%}
        {%- do adapter.create_schema(api.Relation.create(database=target.database, schema=clone_schema)) -%}

        {%- set cloned, views, missing = [], [], [] -%}
        {%- for node in graph.sources.values() | sort(attribute='unique_id') if node.package_name == project_name -%}
            {%- set name = node.source_name ~ '.' ~ node.name -%}
            {%- set prod = adapter.get_relation(database=node.database, schema=node.schema, identifier=node.identifier) -%}
            {%- set clone = api.Relation.create(
                database=target.database, schema=clone_schema,
                identifier=source_clone_identifier(node.source_name, node.name)) -%}
            {%- set existing = adapter.get_relation(database=clone.database, schema=clone.schema, identifier=clone.identifier) -%}
            {%- if prod is none -%}
                {%- do missing.append(name ~ ' (' ~ node.relation_name ~ ')') -%}
            {%- elif prod.is_view -%}
                {%- if existing is not none and not existing.is_view -%}{% do adapter.drop_relation(existing) %}{%- endif -%}
                {%- do run_query('create or replace view ' ~ clone ~ ' as select * from ' ~ prod) -%}
                {%- do views.append(name) -%}
            {%- else -%}
                {%- if existing is not none and existing.is_view -%}{% do adapter.drop_relation(existing) %}{%- endif -%}
                {%- do adapter.dispatch('shallow_clone_table')(clone, prod, existing if existing is not none and not existing.is_view else none) -%}
                {%- do cloned.append(name) -%}
            {%- endif -%}
        {%- endfor -%}

        {%- do print("Shallow-cloned " ~ cloned | length ~ " source table(s) into " ~ clone_schema ~ ":") -%}
        {%- for name in cloned %}{% do print("  " ~ name) %}{% endfor -%}
        {%- if views -%}
            {%- do print("Skipped " ~ views | length ~ " view(s), not cloned; they read prod through a view of the same name:") -%}
            {%- for name in views %}{% do print("  " ~ name) %}{% endfor -%}
        {%- endif -%}
        {%- if missing -%}
            {{ exceptions.raise_compiler_error("Source tables not found: " ~ missing | join(', ')) }}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}
