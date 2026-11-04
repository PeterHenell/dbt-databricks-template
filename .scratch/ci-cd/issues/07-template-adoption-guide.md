# 07: Template adoption guide

**What to build:** A team can create a new data product repo from this template and get to a first release by following one README.

**Blocked by:** dev-environment#01–04, ci-cd#01–06

**Status:** done

- [x] Explains how to rename the template to a data product (the single product variable and anything else that must change)
- [x] Lists what the platform team must provide: team catalog, product dev and prod catalogs, dev-workspace read access to prod catalogs, team and product identities, OIDC federation policies, dev SQL warehouse
- [x] Daily developer workflow: `make setup`, source modes and `make clone-sources`, `dbt build`, `make build-changed`, `make clean-dev`
- [x] Release workflow: MR → merge → GitLab release → product dev test → manual `deploy-prod`
- [x] Rollback, and the documented-only hotfix route (see ADR 0007)
- [x] Uses the vocabulary in `GLOSSARY.md`

## Comments

**2026-11-04 (pending decision, dev-environment#07):** If dev-environment#07 is accepted, adopting means creating a repo from a slim template (dbt code, `platform.toml`, `packages.yml`, stubs, thin Makefile, `devcontainer.json`, 5-line `.gitlab-ci.yml`), and the guide must explain the platform version policy (automatic 1.x updates, opt-in major versions, pinning).

**2026-11-04 (implementation):**
- `README.md` is the adoption guide: platform prerequisites, renaming (every file with the product name; `tests/test_bundle.py` checks the names match), settings to fill in, GitLab settings, daily workflow, MR → merge → release → product dev → `deploy-prod`, rollback and hotfix.
- New glossary terms: release artifact, team identity, product identity, MR build.
- If dev-environment#07 is accepted, the guide needs the slim-template version described there.
