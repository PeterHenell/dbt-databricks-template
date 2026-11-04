{#
  LOCAL SPARK ENGINE ONLY (local/). Never used on Databricks: dbt-databricks dispatches
  to its own `databricks__` macros before any `spark__` one.

  dbt-spark enforces a contract's `not_null` constraints with
  `ALTER TABLE ... CHANGE COLUMN ... SET NOT NULL`, which open-source Delta Lake
  refuses on an existing column ("Cannot change nullable column to non-nullable").
  Locally the same rule is enforced as a CHECK constraint instead.
#}
{% macro spark__alter_column_set_constraints(relation, column_dict) %}
    {%- for column_name in column_dict -%}
        {%- for constraint in column_dict[column_name]['constraints'] -%}
            {%- if constraint.type == 'not_null' -%}
                {%- set quoted_name = adapter.quote(column_name) if column_dict[column_name]['quote'] else column_name -%}
                {%- call statement() -%}
                    alter table {{ relation }} add constraint {{ column_name }}_not_null check ({{ quoted_name }} is not null)
                {%- endcall -%}
            {%- else -%}
                {{ exceptions.warn('Invalid constraint for column ' ~ column_name ~ '. Only `not_null` is supported.') }}
            {%- endif -%}
        {%- endfor -%}
    {%- endfor -%}
{% endmacro %}
