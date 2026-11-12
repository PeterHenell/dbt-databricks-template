# dbtp

The setup, developer-environment and deployment tooling for dbt data products on
Databricks, as one Python package with one command: `dbtp`.

It lives in `tools/dbtp/` of the template for now, as a uv workspace member of the
product repository, but it is written to be moved into a repository of its own:
it imports nothing from the product repository, and it finds
the repository it works on at run time.

## How a product repository uses it

- `pyproject.toml` depends on `dbtp`; `uv sync` installs it with dbt.
- A developer sets up a clone with `uv run dbtp init`. The `Makefile` has the
  developer's daily commands and forwards to it. The CI pipeline calls the CI-only commands (`release …`,
  `bundle …`, `mr-build`) as `uv run dbtp …` directly.
- `dbtp` works on the nearest directory upwards from the working directory that
  has a `dbt_project.yml`. `--project-dir` or `$DBTP_PROJECT_DIR` override that.

What dbtp reads from the product repository:

| File | For |
|---|---|
| `dbt_project.yml` | the data product name (`name`, repeated in `profile`) |
| `config/dev-environment.toml` | dev workspace host, SQL warehouse, team and product dev catalogs |
| `profiles.yml` (written by `dbtp init`) | the developer's alias |
| `deploy/profiles.yml` | `parse`, `mr-build` (deployment profile, ADR 0002) |
| `databricks.yml`, `resources/` | `bundle …`, `release …` |
| `local/compose.yml` | `local …` |
| `.devcontainer/Dockerfile` | `ci_tools.py` reads the uv and Databricks CLI version pins |

The dbt macros the commands call (`clone_sources`, `drop_personal_environment`,
`drop_mr_environment`) are in the `dbt_platform` dbt package (`tools/dbt_platform/`),
which the product repository installs with `dbt deps`.

## Commands

```text
dbtp init [OPTIONS] [--alias A] [--no-profile] [--yes]
                                     repository settings (product name, dev settings,
                                     databricks.yml), then CLI login check, profiles.yml, dbt deps
dbtp clone-sources                   (re)create your shallow source clones
dbtp clean-dev                       drop your personal environment, after confirmation
dbtp build-changed [-- DBT_ARGS]     state:modified+ build, deferring to product dev
dbtp parse                           dbt deps, then offline dbt parse with the deployment profile
dbtp local up|sources|sql|down|clean local Spark engine (containers, run on the host)
dbtp local dbt [DBT_ARGS]            dbt in the local engine (default: build), after dbt deps on the host
dbtp release build [--version V]     build and unpack the release artifact by hand
dbtp release check-tag|publish|fetch CI: release pipeline steps
dbtp bundle validate|deploy|run -t T Databricks Asset Bundle (deploys from the artifact)
dbtp mr-build [-- DBT_ARGS]          CI: drop <product>__mr__*, full build into it
```

Two files are not part of the CLI, because they run where dbtp isn't installed:

- `src/dbtp/jobs/publish_dbt_artifacts.py` runs as a task of the Databricks job.
  The release artifact ships it, and `resources/dbt_job.yml` points at it. It needs
  only the Databricks SDK and must not import dbtp.
- `src/dbtp/ci_tools.py` installs uv and the Databricks CLI in CI, with the image's
  plain `python3` and the standard library only, before uv (and so dbtp) exists.

## Tests

`uv run pytest tools/dbtp/tests` (also part of `make test-tooling`). They need no
product repository and no Databricks. Tests that check the template's own files
(bundle, deploy profile, macros, artifact contents) stay in the product
repository's `tests/`.
