-- Small stand-in for Databricks' samples.tpch (same table and column names and
-- types as the columns the project uses), for the local Spark engine only.
-- Run by `make local-sources`. Some customers have no orders, on purpose.
create schema if not exists tpch;

create or replace table tpch.customer using delta as
select
    id as c_custkey,
    concat('Customer#', lpad(cast(id as string), 9, '0')) as c_name,
    cast(id % 25 as bigint) as c_nationkey,
    cast((id * 37 % 10000) / 100.0 as decimal(18, 2)) as c_acctbal,
    element_at(array('AUTOMOBILE', 'BUILDING', 'FURNITURE', 'HOUSEHOLD', 'MACHINERY'), cast(id % 5 + 1 as int)) as c_mktsegment
from range(1, 1001);

create or replace table tpch.orders using delta as
select
    id as o_orderkey,
    id % 900 + 1 as o_custkey,
    element_at(array('O', 'F', 'P'), cast(id % 3 + 1 as int)) as o_orderstatus,
    cast((id * 7919 % 500000) / 100.0 as decimal(18, 2)) as o_totalprice,
    date_add(date'1992-01-01', cast(id % 2400 as int)) as o_orderdate
from range(1, 10001);
