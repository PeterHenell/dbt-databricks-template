# 05: `make build-changed` (deferred build)

**What to build:** A developer can build only the models they changed, with references to unchanged models resolved against the latest release candidate in product dev, instead of rebuilding the whole project.

**Blocked by:** 01 (Minimal end-to-end skeleton), ci-cd#02 (Job runs publish dbt artifacts)

**Status:** done (Databricks run pending ci-cd#02)

- [x] `make build-changed` downloads `latest/manifest.json` from the product dev catalog's `_dbt_artifacts.state` volume using the developer's own login
- [x] It runs `dbt build --select state:modified+ --defer --state <downloaded>` into the developer's personal environment
- [x] Unchanged upstream models are read from the product dev catalog
- [x] A clear error if no product dev manifest exists yet (no successful product dev run)

## Comments

**2026-11-04 (implementation):**
- `scripts/build_changed.py` (`make build-changed`, extra dbt args via `ARGS="..."`): checks the CLI login, downloads `dbfs:/Volumes/<product_dev>/_dbt_artifacts/state/latest/manifest.json` to `target/product-dev-state/` with `databricks fs cp`, then runs `dbt build --select state:modified+ --defer --state target/product-dev-state`.
- The product dev catalog name is a new setting, `[catalogs] product_dev` in `config/dev-environment.toml`.
- `fs cp` has no `--host` flag, so the script sets `DATABRICKS_HOST`, `DATABRICKS_AUTH_TYPE=databricks-cli` and an empty config file: it always uses the developer's U2M login for the dev workspace, whatever profiles `~/.databrickscfg` holds.
- "No manifest yet" is recognised from the CLI's error text ("not exist"/"not found"/"no such"); the exact Databricks wording is unverified. Other errors are shown as they are.
- Verified on the local Spark engine: built a prod-style deployment into plain layer schemas, used its manifest as state, dropped the personal environment, changed `int_orders_aggregated_to_customer` only. The build ran 8 of 20 nodes; unchanged `stg_*` refs resolved to `staging.*`, the downstream `customers` versions read the personal intermediate model. Download step unit-tested against a fake CLI.
- **Not verified on Databricks:** needs ci-cd#02 (job runs publishing artifacts) first.
