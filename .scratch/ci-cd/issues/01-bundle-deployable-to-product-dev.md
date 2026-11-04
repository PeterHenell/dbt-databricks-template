# 01: Bundle deployable to product dev by hand

**What to build:** The dbt project is wrapped in a Databricks Asset Bundle with one job, so it can be deployed and run in the product dev catalog (and later prod) without anyone's personal profile.

**Blocked by:** dev-environment#01 (Minimal end-to-end skeleton)

**Status:** ready-for-agent

- [ ] A bundle defines one job with a dbt task that uses the committed prod-style profile in `deploy/` via `--profiles-dir deploy` (see ADR 0002)
- [ ] Bundle targets `dev` (dev workspace, product dev catalog, no schedule) and `prod` (prod workspace, product prod catalog, cron schedule)
- [ ] Nothing environment-specific is hard-coded outside the bundle targets and environment variables (see ADR 0008)
- [ ] The job runs on serverless or SQL warehouse compute suited to SQL-only models
- [ ] `make` targets validate and deploy the bundle for a given target, and start a run
- [ ] Deploying to `dev` and running the job by hand builds the sample project into the product dev catalog's `staging`, `intermediate` and `vN` schemas

## Comments

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 proposes moving the bundle to a central platform repo: the bundle and `deploy/profiles.yml` would be rendered from central templates plus the product's `platform.toml` when the release artifact is built, not committed in each repo (conflicts with the first criterion and ADR 0002). Until 07 is triaged, build it as written, but keep everything product-specific in variables so it can become a template.
