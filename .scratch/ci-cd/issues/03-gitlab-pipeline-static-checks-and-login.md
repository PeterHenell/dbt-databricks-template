# 03: GitLab pipeline with static checks and Databricks login

**What to build:** Every MR and every merge to `main` runs the static checks in GitLab, and GitLab jobs can log in to Databricks without stored secrets.

**Blocked by:** 01 (Bundle deployable to product dev by hand)

**Status:** ready-for-agent

- [ ] `.gitlab-ci.yml` only calls `make` targets; all logic lives in the Makefile and scripts
- [ ] CI uses a standard Python image, installs tools from the `uv` lockfile with caching, and uses a pinned Databricks CLI version
- [ ] MR and `main` pipelines run lint (SQL and YAML), `dbt parse`, and bundle validation
- [ ] There is a security-scan stage, using GitLab's built-in scanners where available, with a placeholder otherwise
- [ ] GitLab jobs log in to Databricks with OIDC workload identity federation. It is confirmed that Databricks accepts GitLab as an issuer, and the federation policy the platform team must create is documented
- [ ] The fallback (OAuth client ID and secret in masked, protected CI variables) is documented
- [ ] Merging to `main` deploys nothing

## Comments

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 proposes that pipeline jobs live in a central GitLab CI/CD component (`include: component: …@1`) running a central platform image, instead of `.gitlab-ci.yml` calling this repo's `make` targets in a standard Python image (conflicts with the first two criteria). Check the status of 07 before implementing; if 07 is still open, ask the user which to follow.
