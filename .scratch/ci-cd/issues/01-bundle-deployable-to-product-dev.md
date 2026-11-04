# 01: Bundle deployable to product dev by hand

**What to build:** The dbt project is wrapped in a Databricks Asset Bundle with one job, so it can be deployed and run in the product dev catalog (and later prod) without anyone's personal profile.

**Blocked by:** dev-environment#01 (Minimal end-to-end skeleton)

**Status:** done (deploy and run on Databricks not yet tried)

- [x] A bundle defines one job with a dbt task that uses the committed prod-style profile in `deploy/` via `--profiles-dir deploy` (see ADR 0002)
- [x] Bundle targets `dev` (dev workspace, product dev catalog, no schedule) and `prod` (prod workspace, product prod catalog, cron schedule)
- [x] Nothing environment-specific is hard-coded outside the bundle targets and environment variables (see ADR 0008)
- [x] The job runs on serverless or SQL warehouse compute suited to SQL-only models
- [x] `make` targets validate and deploy the bundle for a given target, and start a run
- [ ] Deploying to `dev` and running the job by hand builds the sample project into the product dev catalog's `staging`, `intermediate` and `vN` schemas

## Comments

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 proposes moving the bundle to a central platform repo: the bundle and `deploy/profiles.yml` would be rendered from central templates plus the product's `platform.toml` when the release artifact is built, not committed in each repo (conflicts with the first criterion and ADR 0002). Until 07 is triaged, build it as written, but keep everything product-specific in variables so it can become a template.

**2026-11-04 (implementation):**
- dev-environment#07 was still `needs-triage`; the user chose to build this as written, in this repo, keeping product-specific values in variables/targets so it can later become a template.
- `databricks.yml` (targets `dev`/`prod`, only place with environment values; `run_as` the target's product identity; prod gets the cron schedule) and `resources/dbt_job.yml` (job `dbt_build`: dbt task with `profiles_directory: deploy`, serverless environment pinned to the `uv.lock` versions; models run on the target's SQL warehouse).
- `deploy/profiles.yml` changed: no more client-id/secret env vars. It uses `DBT_HOST` + `DBT_ACCESS_TOKEN` (Databricks sets both for a dbt task's run-as identity; Databricks' own `dbt-sql` bundle template relies on them) and `var('deploy_catalog')`/`var('deploy_warehouse_id')` passed by the job's command. With a custom profile the dbt task must not set `warehouse_id` (Databricks docs), hence the vars. Checked offline that `var()` works in the profile (`dbt ls`). Added target `mr` for ci-cd#04.
- `make bundle-validate|bundle-deploy|bundle-run TARGET=…`. Deploys always go from the unpacked release artifact (`make artifact`, `scripts/release.py`), so a hand deploy ships what a release ships and no repo-only files get uploaded.
- Verified offline: `databricks bundle validate -t dev|prod` against a fake workspace API (`tests/mock_databricks.py`, `tests/test_bundle.py`); consistency tests (bundle name, pins vs `uv.lock`, `dev` target vs `config/dev-environment.toml`).
- **Not verified:** a real deploy and run (last criterion). Docs: `docs/ci-cd.md`.
