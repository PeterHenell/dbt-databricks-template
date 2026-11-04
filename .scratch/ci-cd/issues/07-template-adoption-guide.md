# 07: Template adoption guide

**What to build:** A team can create a new data product repo from this template and get to a first release by following one README.

**Blocked by:** dev-environment#01–04, ci-cd#01–06

**Status:** ready-for-agent

- [ ] Explains how to rename the template to a data product (the single product variable and anything else that must change)
- [ ] Lists what the platform team must provide: team catalog, product dev and prod catalogs, dev-workspace read access to prod catalogs, team and product identities, OIDC federation policies, dev SQL warehouse
- [ ] Daily developer workflow: `make setup`, source modes and `make clone-sources`, `dbt build`, `make build-changed`, `make clean-dev`
- [ ] Release workflow: MR → merge → GitLab release → product dev test → manual `deploy-prod`
- [ ] Rollback, and the documented-only hotfix route (see ADR 0007)
- [ ] Uses the vocabulary in `GLOSSARY.md`
