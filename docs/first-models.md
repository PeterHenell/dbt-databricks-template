# Building your first models

This guide takes you from the sample models that come with the template to models of your own. It assumes your environment is set up as the [README](../README.md) describes: the repository is initialized (`uv run dbtp init`), you are in the dev container, and `make setup` has run. Every command runs in the dev container's terminal, from the repository root.

In the examples, `<product>` is your data product name (the `name` in `dbt_project.yml`), `<alias>` is your developer alias (the one `make setup` asked for, in the `schema` line of your `profiles.yml`), and `<team_catalog>` is the team catalog from `config/dev-environment.toml`.

You will:

1. build the samples and look at the results;
2. add a new source table;
3. add a staging model for it, with tests;
4. use it in the published interface;
5. learn how the sample seed and unit test work;
6. check your work and open a merge request;
7. replace the samples with your own sources.

## 1. Build the samples and look at the results

```sh
make clone-sources     # your own shallow clones of the sample sources
make build             # build and test everything into your personal environment
```

The first dbt command opens a browser window to log dbt in to Databricks; sign in with your own account. `make build` runs `dbt build`: it loads the seed, builds every model and runs every test, in dependency order. It ends with a line like `Done. PASS=26 WARN=0 ERROR=0 SKIP=0`.

Everything went into your **personal environment**: schemas in the team catalog that only you write to.

| Schema | What is in it | Made from |
|---|---|---|
| `<product>__<alias>__src_clone` | Shallow clones of the sources (`tpch__customer`, `tpch__orders`) | `make clone-sources` |
| `<product>__<alias>__seeds` | `order_statuses`, loaded from a CSV file | `seeds/order_statuses.csv` |
| `<product>__<alias>__staging` | `stg_tpch__customers`, `stg_tpch__orders` (views) | `models/staging/tpch/` |
| `<product>__<alias>__intermediate` | `int_orders_aggregated_to_customer` (view) | `models/intermediate/` |
| `<product>__<alias>__v1`, `…__v2` | `customers`, in two versions (tables) | `models/published/` |

Look at the data in the terminal with `dbt show`, which runs a model's query and prints the first rows:

```sh
uv run dbt show --select customers           # the latest version (v2)
uv run dbt show --select order_statuses      # the seed
```

Or open the SQL editor in the Databricks workspace and query the tables, e.g.

```sql
select * from <team_catalog>.<product>__<alias>__v2.customers limit 10;
```

### How the sample fits together

```text
samples.tpch.customer ──> stg_tpch__customers ───────────────────────────────┐
samples.tpch.orders ────> stg_tpch__orders ──> int_orders_aggregated_to_customer ──> customers (v1, v2)
seeds/order_statuses.csv ─────────────────────┘
```

- **Sources** (`models/staging/tpch/_tpch__sources.yml`) declare the tables the product reads, here Databricks' built-in `samples.tpch`. Models read them with `{{ source('tpch', 'orders') }}`, never with a table name in the SQL.
- **Staging** (`models/staging/<source>/`): one view per source table, named `stg_<source>__<entity>`. It only renames and casts columns to the project's conventions, without joins or business logic.
- **Intermediate** (`models/intermediate/`): `int_` models with the business logic, built from staging models and seeds.
- **Published** (`models/published/`): what consumers of the data product read. These models are versioned and have an enforced contract (more in step 4).
- **Seeds** (`seeds/`): small CSV files of lookup data that dbt loads as tables.

Models refer to each other with `{{ ref('model_name') }}`. That is how dbt knows the build order, and how it puts each model in the right schema for whoever runs it.

## 2. Add a source table

The sample reads two tables of `samples.tpch`. Add a third: `nation`, which names the nation that `stg_tpch__customers.nation_id` points to.

In `models/staging/tpch/_tpch__sources.yml`, add the table under `tables:`:

```yaml
      - name: nation
        description: One row per nation.
        columns:
          - name: n_nationkey
            data_tests: [unique, not_null]
```

Your builds read your clones of the sources, not prod (that's the default **source mode**, `clone`), so make a clone of the new table:

```sh
make clone-sources
```

It prints the tables it cloned; `tpch.nation` is now among them.

## 3. Add a staging model, with tests

Create `models/staging/tpch/stg_tpch__nations.sql`:

```sql
select
    n_nationkey as nation_id,
    n_name as nation_name,
    n_regionkey as region_id
from {{ source('tpch', 'nation') }}
```

Describe and test it in `models/staging/tpch/_tpch__models.yml`, under `models:`:

```yaml
  - name: stg_tpch__nations
    description: Nations, renamed to project conventions.
    columns:
      - name: nation_id
        data_tests: [unique, not_null]
      - name: nation_name
        data_tests: [not_null]
```

Every model gets a description, and its key gets `unique` and `not_null` tests. Build the new model and run its tests, then look at it:

```sh
make build SELECT=stg_tpch__nations
uv run dbt show --select stg_tpch__nations
```

`SELECT` takes any dbt selector: `SELECT=+customers` builds a model and everything upstream of it, `SELECT=stg_tpch__nations+` a model and everything downstream.

You can also make customers' nations a tested relationship: in the same file, under `stg_tpch__customers`, add

```yaml
      - name: nation_id
        data_tests:
          - relationships:
              arguments:
                to: ref('stg_tpch__nations')
                field: nation_id
```

and run `make test SELECT=stg_tpch__customers`.

## 4. Use it in the published interface

Consumers read the **published interface**: the `customers` table in schema `v1` or `v2`. Its columns and types are a contract: dbt refuses to build the model if its result doesn't have exactly the columns and types declared in `models/published/_published.yml`. Adding a column is a non-breaking change, so it goes into the current version, `v2`. Removing or renaming a column is a breaking change, which needs a new version ([`published-interface.md`](published-interface.md)).

Add `nation_name` to `customers` v2. In `models/published/customers_v2.sql`, add the column and the join:

```sql
select
    customers.customer_id,
    customers.customer_name,
    nations.nation_name,
    cast(coalesce(orders.number_of_orders, 0) as bigint) as number_of_orders,
    cast(coalesce(orders.number_of_open_orders, 0) as bigint) as number_of_open_orders,
    cast(coalesce(orders.lifetime_value, 0) as decimal(18, 2)) as total_order_value,
    orders.first_order_date,
    orders.most_recent_order_date
from {{ ref('stg_tpch__customers') }} as customers
left join {{ ref('int_orders_aggregated_to_customer') }} as orders
    on customers.customer_id = orders.customer_id
left join {{ ref('stg_tpch__nations') }} as nations
    on customers.nation_id = nations.nation_id
```

In `models/published/_published.yml`, declare the column with its type under the model's `columns:` (after `customer_name`):

```yaml
      - name: nation_name
        data_type: string
```

The columns listed there are shared by all versions; each version picks its own with `include`/`exclude`. `v1` includes all columns except those it excludes, so exclude the new one from `v1`, which must not change:

```yaml
    versions:
      - v: 1
        deprecation_date: 2027-06-30
        columns:
          - include: all
            exclude: [total_order_value, number_of_open_orders, nation_name]
```

Build both versions and everything they need:

```sh
make build SELECT=+customers
uv run dbt show --select customers
```

If you forget the YAML or get a type wrong, the build stops with a contract error that lists the expected and actual columns.

## 5. The seed and the unit test

**The seed.** `seeds/order_statuses.csv` maps the one-letter order status codes in the source to names, and says which statuses count as open:

```text
order_status,order_status_name,is_open
F,Fulfilled,false
O,Open,true
P,Partially fulfilled,true
```

`seeds/_seeds.yml` describes it, sets its column types and tests it like a model. `int_orders_aggregated_to_customer` reads it with `{{ ref('order_statuses') }}` to count each customer's open orders. `make build` loads it before the models that use it; `make build SELECT=order_statuses` loads only the seed. Seeds are for small lookup lists that change rarely and are reviewed in merge requests, not for data that comes from another system: that is a source. To add one, put a CSV file in `seeds/` and an entry in `seeds/_seeds.yml`. If you change a seed's columns, reload it with `make build SELECT=<seed> ARGS="--full-refresh"`.

**The unit test.** Data tests (`unique`, `not_null`, `relationships`) check the data a model produced. A unit test checks a model's logic on a few rows you write yourself, before the model is built. The example is under `unit_tests:` in `models/intermediate/_intermediate.yml`: it gives `int_orders_aggregated_to_customer` three orders and the three statuses, and states the two customer rows it must return. Run only the unit tests with

```sh
make test SELECT=test_type:unit
```

Write unit tests for logic that is easy to get wrong: aggregations, conditions, date arithmetic. List only the input columns the model uses.

## 6. Check your work and open a merge request

Before you push, run the checks the MR pipeline runs first:

```sh
make lint parse
```

`lint` checks the SQL style (sqlfluff) and the YAML (yamllint). `parse` checks that the project is valid as the deployment sees it, without connecting to Databricks. Then commit, push your branch and open a merge request. The pipeline runs the same checks, the tooling tests, and then a full `dbt build` from the prod sources into the shared MR schemas (`<product>__mr__*`). A green MR means the change is ready to merge. Deploying is a separate step: a release ([README](../README.md), "From change to prod").

## 7. Replace the samples with your own sources

When you are ready to build your real product, replace the samples one layer at a time:

1. **Sources.** Add a folder `models/staging/<source>/` with `_<source>__sources.yml` for each real source. Put each source's catalog and schema in variables in `dbt_project.yml` (like `tpch_catalog` and `tpch_schema`), and set `database` only on Databricks, as the sample does:

   ```yaml
   database: "{{ var('crm_catalog') if target.type == 'databricks' else none }}"
   schema: "{{ var('crm_schema') }}"
   ```

   Run `make clone-sources` after adding sources. Your team needs read access to them (README, section 1).
2. **Staging and intermediate models** for the new sources, as in steps 3 to 5.
3. **Published models.** A new product starts its published interface at version 1: `models/published/<model>_v1.sql`, and in the YAML `latest_version: 1` and `versions: [{v: 1}]`, with a `data_type` for every column. Copy the shape of `_published.yml`.
4. **Delete the samples** once nothing refers to them: `models/staging/tpch/`, `models/intermediate/int_orders_aggregated_to_customer.sql`, `models/published/customers_v*.sql`, their entries in the YAML files, `seeds/order_statuses.csv` and its entry, and the `tpch_*` variables in `dbt_project.yml`. If you use the local engine, replace `local/tpch.sql` with stand-ins for your own sources.
5. `make clean-dev` drops your whole personal environment, so the old sample tables don't linger, and `make build` builds it again from scratch.

### Rules that keep the project working

- Put every model in one of the layer folders. Each folder's schema is set with `+schema` in `dbt_project.yml`; a new folder needs its own `+schema` line, and `make test-tooling` fails if a model has none.
- Never write a catalog or schema name in a model. Use `source()` and `ref()`.
- Published models are always versioned and have a `data_type` on every column. An unversioned published model stops the build with an error that says so.
- `make build` only ever writes to your own `<product>__<alias>__*` schemas, so try things freely.

More: [`workflows.md`](workflows.md) for every workflow from setup to rollback, [`published-interface.md`](published-interface.md) for versions, and the [dbt documentation](https://docs.getdbt.com/docs/build/projects).
