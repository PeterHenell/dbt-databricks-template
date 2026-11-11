-- Stand-ins for the product's sources, for the local Spark engine only (the
-- local engine can't read Databricks tables). Run by `make local-sources`.
-- Give each table the same schema, table and column names and types as the
-- prod source, and a few rows.
--
-- The sample models generate their own rows and read no source. The table below
-- is the source that docs/first-models.md adds as an example: a small copy of
-- Databricks' built-in samples.tpch.nation.
create schema if not exists tpch;

create or replace table tpch.nation using delta as
select
    id as n_nationkey,
    concat('NATION_', cast(id as string)) as n_name,
    cast(id % 5 as bigint) as n_regionkey,
    'stand-in row' as n_comment
from range(0, 25);
