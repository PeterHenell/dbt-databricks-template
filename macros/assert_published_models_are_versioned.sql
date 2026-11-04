{#
  Run on every run/build (on-run-start): every model in the published layer must use
  dbt model versions, so it is built into `vN` schemas (ADR 0003).
#}
{% macro assert_published_models_are_versioned() %}
    {%- if execute -%}
        {%- set unversioned = [] -%}
        {%- for node in graph.nodes.values() -%}
            {%- if node.resource_type == 'model' and node.package_name == project_name
                  and node.config.schema == 'published' and node.version is none -%}
                {%- do unversioned.append(node.name) -%}
            {%- endif -%}
        {%- endfor -%}
        {%- if unversioned -%}
            {{ exceptions.raise_compiler_error(
                "Published models must be versioned (ADR 0003), add `versions:` to their YAML: "
                ~ unversioned | join(', ') ~ ". See docs/published-interface.md."
            ) }}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}
