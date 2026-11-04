# The published interface and its versions

Consumers read the published interface from one schema per major contract version: `v1`, `v2`, … in the product catalog (`<product>__<alias>__vN` in your personal environment). Tables keep their plain names: `v2.customers`, not `customers_v2`.

The whole interface is versioned together (ADR 0003): a breaking change to **any** published model means a new major version for **all** of them, so every `vN` schema holds the complete product.

## How it is built

- Models in `models/published/` use [dbt model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions). Version N of a model lives in `<model>_vN.sql`.
- `macros/generate_schema_name.sql` puts version N in layer `vN`; `macros/generate_alias_name.sql` keeps the plain model name.
- Every published model has an enforced contract (`data_type` on every column).
- A published model without `versions:` fails the run (`macros/assert_published_models_are_versioned.sql`, run on run start).
- `ref('customers')` resolves to the `latest_version`; pin an older one with `ref('customers', v=1)`.

## Adding a major version (N → N+1)

For **every** model in `models/published/`:

1. Copy `<model>_vN.sql` to `<model>_vN+1.sql` and make the change.
2. In the model's YAML, add `- v: N+1` under `versions:` with its column `include`/`exclude` list, and set `latest_version: N+1`.
3. Give `- v: N` a `deprecation_date` that leaves consumers time to move.

Then `uv run dbt build --select published` and check that both `vN` and `vN+1` build and pass their tests.

## Retiring a version

Both versions are built until the old one's `deprecation_date`. After that date dbt warns on every parse ("has passed its deprecation date"). Then, for every published model, delete the old `<model>_vN.sql` and its `- v: N` entry. The `vN` schema is left in the catalog; drop it by hand once consumers no longer use it.
