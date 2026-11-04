# 04: MR full build

**What to build:** A passing MR means the code builds and its tests pass: every MR pipeline builds the whole project in the team catalog, using the team identity.

**Blocked by:** 03 (GitLab pipeline with static checks and Databricks login)

**Status:** done (not yet run against the team catalog)

- [x] MR pipelines log in as the team identity
- [x] Each MR build first drops the schemas `<product>__mr__*` in the team catalog, then runs a full `dbt build` (no `--defer`) into `<product>__mr__<layer>`
- [x] MR builds read prod sources directly
- [x] All MR builds share `resource_group: mr-build`, so only one runs at a time
- [x] A failing model or test fails the MR pipeline
- [x] The schema naming macro supports this MR target without a developer alias
- [x] Using `--defer` against product dev to reduce cost is noted as a later improvement (see ADR 0009)

## Comments

**2026-11-04 (implementation):**
- `make ci-mr-build` → `scripts/mr_build.py`: gets an OAuth token from the SDK's credential chain (CI login) and passes it to dbt as `DBT_ACCESS_TOKEN`; dev workspace, team catalog and warehouse come from `config/dev-environment.toml`; runs `dbt deps`, `run-operation drop_mr_environment` (new `macros/mr_environment.sql`, shares the drop logic with `make clean-dev`; refuses any target but `mr`/`<product>__mr`), then `dbt build --target mr` with no `--defer`. Stops at the first non-zero exit, so a failing model or test fails the job.
- `generate_schema_name` needed no change: target `mr` with schema `<product>__mr` gives `<product>__mr__<layer>` (tested with `dbt ls`). Sources: non-personal targets already read prod.
- `resource_group: mr-build`, MR pipelines only. `--defer` is noted as a later improvement in `docs/ci-cd.md`.
- Tests: `tests/test_mr_build.py`, `tests/test_macros.py` (MR drop). **Not verified** against a real team catalog.
