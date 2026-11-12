# dbt_platform

The platform's dbt macros for data products on Databricks, as one dbt package:

| File (`macros/`) | What |
|---|---|
| `generate_schema_name.sql` | One schema per layer: plain `<layer>` in target `prod`, `<target.schema>__<layer>` everywhere else (ADR 0001) |
| `source_modes.sql` | The `source()` override (`dev_source_mode`: prod, clone, sample) and `clone_sources` (`make clone-sources`) (ADR 0005) |
| `personal_environment.sql` | `drop_personal_environment` (`make clean-dev`) and the schema matching it shares with the MR build |
| `mr_environment.sql` | `drop_mr_environment` (`dbtp mr-build`, ADR 0009) |
| `local_spark/` | Local Spark engine only: NOT NULL contracts as CHECK constraints |

It lives in `tools/dbt_platform/` of the template for now, next to the `dbtp` CLI
(`tools/dbtp/`), and is written to move into a repository of its own. It knows nothing about the product: the product name is dbt's
`project_name` (the root project), and the macros only look at the root project's
nodes and sources.

## How a product repository uses it

1. `packages.yml` installs it; `dbt deps` (run by `make setup`, `make parse`, the MR
   build and the release build) puts it in `dbt_packages/dbt_platform`:

   ```yaml
   packages:
     - local: tools/dbt_platform
   ```

   Once it has its own repository, this becomes a `git:` entry with a `revision:`.
   Nothing else in the product repository changes.

2. dbt only takes some overrides from the root project, so the product keeps one-line
   stubs in `macros/dbt_platform.sql` that call the package: `generate_schema_name`,
   `source` and `spark__alter_column_set_constraints`. They
   change only when the package's interface does.

`dbt run-operation clone_sources`, `drop_personal_environment` and
`drop_mr_environment` find the package's macros by name, so dbtp calls them as before.

## Writing macros here

- Call the package's own macros with the package prefix (`dbt_platform.source_clone_schema()`).
  A package macro called from the root project runs in the root project's namespace,
  where unprefixed package macros are not found.
- Dispatch adapter-specific macros in this package's namespace,
  `adapter.dispatch('name', 'dbt_platform')`, so a product can still override them.
- Don't name an override of a dbt or adapter macro `spark__…` or `databricks__…` here.
  dbt searches dispatch packages one at a time, with every adapter prefix in each, so
  a `spark__` macro found in a package searched before `dbt` wins over
  dbt-databricks' own `databricks__` one. Give it a plain name and call it from a stub
  in the root project that hands non-Spark adapters back to their own macro (see
  `local_spark/alter_column_set_constraints.sql`).

## Tests

The macros are tested from the product repository (`tests/test_macros.py`, part of
`make test-tooling`): offline `dbt run-operation` and `dbt parse` runs on the sample
product, no Databricks needed.
