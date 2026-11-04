# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repository is a **git repository template** for dbt projects running on Databricks. Teams create new repos from it, so everything here should be generic, clearly documented, and easy to rename/adapt (avoid hard-coding a specific workspace, catalog, or team name — use placeholders or variables).

The template has two primary functional goals; design decisions should be evaluated against them:

1. **Isolated development environments** — every member of a data engineering team can develop and run dbt against Databricks without affecting teammates or shared environments. A developer's `dbt run`/`dbt build` must only ever write to objects owned by that developer's environment, and the isolation must hold without per-developer manual setup beyond credentials.
2. **Deployment pattern** — a repeatable, automated way to deploy the dbt project to Databricks for shared environments (e.g. test/prod), driven from CI/CD rather than from developer machines.

Beyond those, the template should embody dbt best practices (project layering, naming conventions, testing, documentation) and Databricks-specific best practices for the dbt-databricks adapter.

## Current state

Personal development environments are built (`.scratch/dev-environment/`, tickets 01–06), but only verified offline and on the local Spark engine, not yet on a Databricks workspace. Deployment (`.scratch/ci-cd/`) is not built yet; when it is, document here which tool, which targets and what CI triggers it. Do not document conventions here until they exist in the repo.

**Pending decision:** `.scratch/dev-environment/issues/07-central-platform-repository.md` (`needs-triage`) proposes moving the tooling (`scripts/`, the platform macros, `local/`, the dev container image, CI/CD and the bundle) into a central, versioned platform repository. It conflicts with ADR 0002 and with ci-cd#01, #03, #05, #07 and dev-environment#06; each of those carries a note. Read ticket 07's "For the agent picking this up" before working on any of them, and don't implement 07 until the user has answered its open questions.

**Not yet verified on Databricks** (details in each ticket's `## Comments`): the OAuth flows (`make setup`, dbt's browser login, inside the dev container), `make clean-dev`, `make clone-sources` (incl. whether `samples.tpch` can be shallow-cloned), `make build-changed` (needs ci-cd#02 first; the "no manifest" CLI error text is guessed), and opening the dev container in VS Code or Docker Desktop. Deviation to keep in mind: source views get a proxy view in the clone schema instead of resolving to the prod name (dev-environment#04).

## Commands

The supported way to run the toolkit is the dev container (`.devcontainer/`, see `docs/dev-container.md`); the Makefile and scripts assume Linux + bash. Python tools are pinned in `pyproject.toml` / `uv.lock`; run dbt through `uv run`.

```sh
make setup                                    # uv sync, check Databricks CLI login, write ./profiles.yml, dbt deps
make clone-sources                            # (re)create your shallow clones of the sources (default source mode: clone)
uv run dbt build                              # build + test everything into your personal environment
uv run dbt build --select customers           # one model (all versions) and its tests
uv run dbt build --select +customers          # a model and everything upstream
uv run dbt test --select stg_tpch__orders     # tests of one model
uv run dbt build --vars '{dev_source_mode: prod}'   # read prod sources directly for this run
make build-changed                            # deferred build: only state:modified+, rest from product dev
make clean-dev                                # drop your whole personal environment (asks first)
make test-tooling                             # pytest: scripts/ and the macros (no Databricks needed)
uv run dbt parse                              # offline check of the project (no connection needed)
```

Prod-style builds use the committed deployment profile and only with `--profiles-dir deploy` (env vars `DBT_DATABRICKS_HOST`, `DBT_DATABRICKS_HTTP_PATH`, `DBT_CATALOG`, `DBT_DATABRICKS_CLIENT_ID`, `DBT_DATABRICKS_CLIENT_SECRET`).

### Local engine (no Databricks)

`local/` runs the project on Apache Spark + Delta Lake in containers, with the Hive metastore in Postgres, through dbt-spark (session method) inside its own image. Run on the host (Podman or Docker), not in the dev container:

```sh
make local-sources                            # start metastore, create the stand-in tpch tables
make local-dbt                                # dbt build into sample_product__local__* (LOCAL_ALIAS=... to change)
make local-dbt ARGS="run-operation clone_sources"
make local-sql                                # Spark SQL shell; make local-down / local-clean
```

It has no Unity Catalog (schema.table only), so project code must not assume catalogs: sources set `database` only when `target.type == 'databricks'`, and adapter-specific macros use `adapter.dispatch` with `databricks__` / `spark__` variants (dbt-databricks dispatches `databricks__` before `spark__`, so `spark__` overrides in `macros/local_spark/` never affect Databricks). A green local build doesn't replace a Databricks build.

## Developer isolation (how it works)

- **Product name** = the dbt project `name` in `dbt_project.yml`; `profile` must repeat it (dbt can't read the profile name from a variable; `scripts/devenv.py` checks they match).
- **Team settings** (dev workspace host, shared SQL warehouse, team catalog) are committed in `config/dev-environment.toml`.
- **`make setup`** (`scripts/setup_dev.py`, helpers in `scripts/devenv.py`) checks `databricks auth token --host <host>`, suggests an alias from the user's name (SCIM `Me`, falling back to `git config user.name`), and writes the gitignored `./profiles.yml` with `schema: <product>__<alias>` in the team catalog, `auth_type: oauth`. dbt-databricks runs its own browser OAuth on the first dbt command; the CLI login is for the Makefile tooling.
- **Schema names** come from one override, `macros/generate_schema_name.sql`: target `prod` (the deploy profile, used for product dev and product prod) → `<layer>`; any other target → `<target.schema>__<layer>`, i.e. `<product>__<alias>__<layer>`. Layers are set per model folder with `+schema` in `dbt_project.yml`.
- **Sources** are located through project variables (`tpch_catalog`, `tpch_schema`), never hard-coded. `macros/source_modes.sql` overrides `source()`: on personal targets (`dev`, `local`) `dev_source_mode` (default `clone`) redirects to `<product>__<alias>__src_clone.<source>__<table>`; all other targets read prod. `make clone-sources` (`clone_sources` macro) makes the shallow clones; source views get a view in the clone schema that reads prod.
- **`make clean-dev`** (`drop_personal_environment` in `macros/personal_environment.sql`) drops exactly `<product>__<alias>` and `<product>__<alias>__*`; it refuses target `prod` and the reserved alias `mr` (MR schemas, ADR 0009).
- **`make build-changed`** (`scripts/build_changed.py`) downloads `latest/manifest.json` from `/Volumes/<product_dev>/_dbt_artifacts/state` with the CLI login and runs `dbt build --select state:modified+ --defer --state target/product-dev-state`. Needs `[catalogs] product_dev` in `config/dev-environment.toml`.

## Project layout

- `models/staging/<source>/` — one view per source table, renamed to conventions (`stg_<source>__<entity>`), sources declared in `_<source>__sources.yml`.
- `models/intermediate/` — `int_` views.
- `models/published/` — the published interface: versioned models (`<model>_vN.sql`) with enforced contracts, built into schema `vN` under the plain model name. `macros/generate_alias_name.sql` drops the `_vN` suffix; an unversioned published model fails on run start. How to add or retire a major version: `docs/published-interface.md`.
- The sample source is Databricks' built-in `samples.tpch`; it stands in for a real product's sources (locally, `local/tpch.sql` creates a small copy).
- All models are Delta (`+file_format: delta`).
- `tests/` — pytest: `test_devenv.py` (setup helpers), `test_build_changed.py` (fake CLI), `test_macros.py` (runs macros through `dbt run-operation` offline).

## Agent skills

### Issue tracker

Issues and specs are tracked as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
