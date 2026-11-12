# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repository is one **data product**: a dbt project on Databricks, created from the team template. The dbt project `name` in `dbt_project.yml` is the data product name. Terms in bold are defined in `GLOSSARY.md`; decisions and their reasons are in `docs/adr/`.

Two rules shape everything here:

1. **Isolated development environments.** A developer's `dbt build` only ever writes to their own **personal environment** (`<product>__<alias>__<layer>` schemas in the team catalog). Never hard-code catalogs or schemas in models; schema names come from the platform macros.
2. **Deployment from CI only.** Shared environments (product dev, product prod) are deployed by the GitLab release pipeline from one release artifact, never from a developer machine.

## Commands

Run everything in the dev container (`.devcontainer/`, see `docs/dev-container.md`); the Makefile and dbtp assume Linux + bash. Python tools are pinned in `pyproject.toml` / `uv.lock`; run dbt and dbtp through `uv run`.

```sh
uv run dbtp init                              # once per new repository: product name + team settings
make setup                                    # uv sync, check Databricks CLI login, write ./profiles.yml, dbt deps
make clone-sources                            # (re)create your shallow clones of the sources
make build                                    # dbt build into your personal environment
make build SELECT=+customers                  # a model and everything upstream (also: make run, test, compile)
make build SOURCE_MODE=prod                   # read prod sources directly for this run
make build ARGS="--full-refresh"              # ARGS goes to dbt as is; `uv run dbt …` works too (same profile)
uv run dbt show --select customers            # preview a model's rows
make build-changed                            # only state:modified+, the rest deferred to product dev
make clean-dev                                # drop your whole personal environment (asks first)
make lint parse                               # sqlfluff + yamllint; offline dbt parse with the deploy profile
make test-tooling                             # pytest: tools/dbtp/tests + tests/ (no Databricks needed)
```

The Makefile holds only the developer's daily commands. CI-only steps are `uv run dbtp …` in `.gitlab-ci.yml`; rarely used commands are in the docs. Don't add CI or one-off targets to the Makefile.

## Project layout and conventions

- `models/staging/<source>/`: one view per source table, renamed to project conventions (`stg_<source>__<entity>`); sources declared in `_<source>__sources.yml` with their prod catalog and schema; set `database` only when `target.type == 'databricks'` (the local engine has no catalogs). Models read sources only through `source()`, never by table name.
- `models/intermediate/`: `int_` views with the business logic.
- `models/published/`: the published interface that consumers read, built into schema `published` under plain model names. Every model here has an enforced contract (`data_type` on every column). There is no built-in versioning (ADR 0010): breaking changes are handled by team review, see `docs/published-interface.md`.
- `seeds/`: small static lookup CSVs, documented and tested in `seeds/_seeds.yml`, built into the `seeds` layer.
- Each folder is a layer with its own schema, set with `+schema` in `dbt_project.yml`. A new model folder needs a `+schema`, otherwise its models fall back to the profile's schema (`tests/test_bundle.py` catches that).
- All models are Delta (`+file_format: delta`).
- Every model gets a description and at least a `unique` + `not_null` test on its key; put logic worth checking under `unit_tests:`.
- The sample models (`models/staging/sample/`) generate a few rows in plain selects and read no source. `local/sources.sql` holds stand-ins of the sources for the local engine. `docs/first-models.md` walks through adding a source and models.

## How it works

- **Personal environments** (`docs/workflows.md`, ADR 0001, 0005): team settings are in `config/dev-environment.toml`. `make setup` writes the gitignored `./profiles.yml` with `schema: <product>__<alias>` in the team catalog. On personal targets (`dev`, `local`) `source()` reads `<product>__<alias>__src_clone.<source>__<table>` (made by `make clone-sources`) unless `dev_source_mode: prod`; all other targets read prod.
- **Deployment** (`docs/ci-cd.md`): a Databricks Asset Bundle (`databricks.yml`, `resources/dbt_job.yml`) with targets `dev` (product dev) and `prod`. MR → static checks + MR build into `<product>__mr__*`; release tag → release artifact → deploy + run in product dev → manual `deploy-prod`. Prod-style builds use `deploy/profiles.yml` only with `--profiles-dir deploy`.
- **Local engine** (`local/`, `make local-*`, on the host, not in the dev container): Spark + Delta in containers, for trying changes without Databricks. A green local build doesn't replace a Databricks build.

## Platform code (maintained by the platform team)

`tools/dbtp/` (the `dbtp` CLI) and `tools/dbt_platform/` (the platform dbt macros, installed by `dbt deps` from `packages.yml`) are maintained by the platform team and will move to their own repository. Don't change them here; report problems to the platform team. The same goes for the one-line stubs in `macros/dbt_platform.sql`, which dbt only accepts in the root project. If you do have to work on them:

- Both must stay movable: no imports from or names of this product; dbtp finds the project at run time, the macros use `project_name` and the root project's nodes only.
- Every Makefile recipe forwards to dbtp or runs one tool; no logic in the Makefile.
- Inside the dbt package, call sibling macros with the `dbt_platform.` prefix and dispatch with `adapter.dispatch(name, 'dbt_platform')`.
- Every dbt run needs `dbt deps` first.

## Status

Built and tested offline and on the local Spark engine. Not yet run on a Databricks workspace or in GitLab: the OAuth logins, `make clone-sources`, `make clean-dev`, `make build-changed`, the dev container in VS Code, and the whole deployment (`docs/ci-cd.md`, "Not verified yet"). Expect small fixes on the first real run.
