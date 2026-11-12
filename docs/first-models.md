# Building your first models

This guide takes you from the sample models that come with the template to models of your own. It assumes your environment is set up as the [README](../README.md) describes: the repository is initialized (`uv run dbtp init`), you are in the dev container, and `make setup` has run. Every command runs in the dev container's terminal, from the repository root.

In the examples, `<product>` is your data product name (the `name` in `dbt_project.yml`), `<alias>` is your developer alias (the one `make setup` asked for, in the `schema` line of your `profiles.yml`), and `<team_catalog>` is the team catalog from `config/dev-environment.toml`.

You will:

1. build the samples and look at the results;
2. add a model, with tests;
3. use it in the published interface;
4. learn how the sample seed and unit test work;
5. check your work and open a merge request;
6. replace the samples with your own sources.

## 1. Build the samples and look at the results

```sh
make build             # build and test everything into your personal environment
```

The first dbt command opens a browser window to log dbt in to Databricks; sign in with your own account. `make build` runs `dbt build`: it loads the seed, builds every model and runs every test, in dependency order. It ends with a line like `Done. PASS=22 WARN=0 ERROR=0 SKIP=0`.

Everything went into your **personal environment**: schemas in the team catalog that only you write to.

| Schema | What is in it | Made from |
|---|---|---|
| `<product>__<alias>__seeds` | `order_statuses`, loaded from a CSV file | `seeds/order_statuses.csv` |
| `<product>__<alias>__staging` | `stg_sample__customers`, `stg_sample__orders` (views) | `models/staging/sample/` |
| `<product>__<alias>__intermediate` | `int_orders_aggregated_to_customer` (view) | `models/intermediate/` |
| `<product>__<alias>__published` | `customers` (table) | `models/published/` |

Look at the data in the terminal with `dbt show`, which runs a model's query and prints the first rows:

```sh
uv run dbt show --select customers           # the published model
uv run dbt show --select order_statuses      # the seed
```

Or open the SQL editor in the Databricks workspace and query the tables, e.g.

```sql
select * from <team_catalog>.<product>__<alias>__published.customers limit 10;
```

### How the sample fits together

```text
stg_sample__customers ──────────────────────────────────────────────┐
stg_sample__orders ──> int_orders_aggregated_to_customer ──> customers
seeds/order_statuses.csv ──┘
```

- **Sample data** (`models/staging/sample/`): the two sample models generate a few customers and orders with a plain `select … from values`, so the template builds without reading any table. They stand in for staging models on real sources, which you add in step 6.
- **Sources** declare the tables the product reads from other systems. Models read them with `{{ source('<source>', '<table>') }}`, never with a table name in the SQL.
- **Staging** (`models/staging/<source>/`): one view per source table, named `stg_<source>__<entity>`. It only renames and casts columns to the project's conventions, without joins or business logic.
- **Intermediate** (`models/intermediate/`): `int_` models with the business logic, built from staging models and seeds.
- **Published** (`models/published/`): what consumers of the data product read. These models have an enforced contract (more in step 3).
- **Seeds** (`seeds/`): small CSV files of lookup data that dbt loads as tables.

Models refer to each other with `{{ ref('model_name') }}`. That is how dbt knows the build order, and how it puts each model in the right schema for whoever runs it.

## 2. Add a model, with tests

Add a third sample model: a list of nations, which names the nation that `stg_sample__customers.nation_id` points to. Like the other two, it generates its rows in a plain select.

Create `models/staging/sample/stg_sample__nations.sql`:

```sql
select
    cast(nation_id as bigint) as nation_id,
    nation_name
from
    values
    (3, 'Denmark'),
    (7, 'Norway'),
    (21, 'Sweden')
        as nations (nation_id, nation_name)
```

Describe and test it in `models/staging/sample/_sample__models.yml`, under `models:`:

```yaml
  - name: stg_sample__nations
    description: A few sample nations, generated in the model's SQL.
    columns:
      - name: nation_id
        data_tests: [unique, not_null]
      - name: nation_name
        data_tests: [not_null]
```

Every model gets a description, and its key gets `unique` and `not_null` tests. Build the new model and run its tests, then look at it:

```sh
make build SELECT=stg_sample__nations
uv run dbt show --select stg_sample__nations
```

`SELECT` takes any dbt selector: `SELECT=+customers` builds a model and everything upstream of it, `SELECT=stg_sample__nations+` a model and everything downstream.

You can also make customers' nations a tested relationship: in the same file, under `stg_sample__customers`'s `columns:`, add

```yaml
      - name: nation_id
        data_tests:
          - relationships:
              arguments:
                to: ref('stg_sample__nations')
                field: nation_id
```

and run `make test SELECT=stg_sample__customers`.

## 3. Use it in the published interface

Consumers read the **published interface**: the `customers` table in schema `published`. Its columns and types are a contract: dbt refuses to build the model if its result doesn't have exactly the columns and types declared in `models/published/_published.yml`. Adding a column is a non-breaking change. Removing or renaming a column is a breaking change, which the team agrees with consumers before it is merged ([`published-interface.md`](published-interface.md)).

Add `nation_name` to `customers`. In `models/published/customers.sql`, add the column and the join:

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
from {{ ref('stg_sample__customers') }} as customers
left join {{ ref('int_orders_aggregated_to_customer') }} as orders
    on customers.customer_id = orders.customer_id
left join {{ ref('stg_sample__nations') }} as nations
    on customers.nation_id = nations.nation_id
```

In `models/published/_published.yml`, declare the column with its type under the model's `columns:` (after `customer_name`):

```yaml
      - name: nation_name
        data_type: string
```

Build it and everything it needs:

```sh
make build SELECT=+customers
uv run dbt show --select customers
```

If you forget the YAML or get a type wrong, the build stops with a contract error that lists the expected and actual columns.

## 4. The seed and the unit test

**The seed.** `seeds/order_statuses.csv` maps the one-letter order status codes in `stg_sample__orders` to names, and says which statuses count as open:

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

## 5. Check your work and open a merge request

Before you push, run the checks the MR pipeline runs first:

```sh
make lint parse
```

`lint` checks the SQL style (sqlfluff) and the YAML (yamllint). `parse` checks that the project is valid as the deployment sees it, without connecting to Databricks. Then commit, push your branch and open a merge request. The pipeline runs the same checks, the tooling tests, and then a full `dbt build` from the prod sources into the shared MR schemas (`<product>__mr__*`). A green MR means the change is ready to merge. Deploying is a separate step: a release ([README](../README.md), "From change to prod").

## 6. Replace the samples with your own sources

When you are ready to build your real product, replace the samples one layer at a time:

1. **Sources.** Sources are the tables the product reads from other systems. For each one, add a folder `models/staging/<source>/` with a file `_<source>__sources.yml` that says where its tables live in prod:

   ```yaml
   version: 2

   sources:
     - name: crm
       description: Customer records from the CRM system.
       # The local Spark engine (local/) has no catalogs, only schema.table.
       database: "{{ 'crm_prod' if target.type == 'databricks' else none }}"
       schema: crm
       tables:
         - name: customers
           columns:
             - name: customer_id
               data_tests: [unique, not_null]
   ```

   Models read a source table with `{{ source('crm', 'customers') }}`, never with its table name. Every build reads the prod location written here, except in your personal environment, where `source()` reads your own shallow clones of the tables instead (the **source mode**, `clone` by default). Make or refresh the clones with `make clone-sources` after adding a source, and whenever you want fresher data. Your team needs read access to the sources (README, section 1).
2. **Staging and intermediate models** for the new sources, as in steps 2 to 4: a staging model selects from `source()` instead of generating its rows.
3. **Published models.** Put the models consumers read in `models/published/<model>.sql`, with a `data_type` for every column in the YAML. Copy the shape of `_published.yml`.
4. **Delete the samples** once nothing refers to them: `models/staging/sample/`, `models/intermediate/int_orders_aggregated_to_customer.sql`, `models/published/customers.sql`, their entries in the YAML files, and `seeds/order_statuses.csv` and its entry. If you use the local engine, put stand-ins for your own sources in `local/sources.sql`.
5. `make clean-dev` drops your whole personal environment, so the old sample tables don't linger, and `make build` builds it again from scratch.

### Rules that keep the project working

- Put every model in one of the layer folders. Each folder's schema is set with `+schema` in `dbt_project.yml`; a new folder needs its own `+schema` line, and `make test-tooling` fails if a model has none.
- Never write a catalog or schema name in a model. Use `source()` and `ref()`.
- Published models have a `data_type` on every column. Treat a change that removes or renames a published column, or changes its type, as breaking: agree it with consumers first.
- `make build` only ever writes to your own `<product>__<alias>__*` schemas, so try things freely.

More: [`workflows.md`](workflows.md) for every workflow from setup to rollback, [`published-interface.md`](published-interface.md) for changing published models, and the [dbt documentation](https://docs.getdbt.com/docs/build/projects).
