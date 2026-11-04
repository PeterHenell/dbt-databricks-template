# 05: Release pipeline: artifact and test in product dev

**What to build:** Creating a GitLab release on a `main` commit packages the project once, deploys that package to product dev, and runs it there as the release's test.

**Blocked by:** 01 (Bundle deployable to product dev by hand), 03 (GitLab pipeline with static checks and Databricks login)

**Status:** done (not yet run in GitLab or on Databricks)

- [x] The pipeline runs on release tags only, and refuses a tag whose commit is not on `main`
- [x] It builds one archive containing the bundle, the dbt project, installed `dbt_packages/` and `deploy/`, with no environment-specific values
- [x] The archive is uploaded to the GitLab generic package registry as package `<product>`, version `<tag>`, file `<product>-<tag>.tar.gz`
- [x] The artifact is written once: re-running the pipeline reuses the existing archive instead of rebuilding it
- [x] Which characters GitLab allows in package versions is checked, and the rule for release tag names is documented
- [x] The unpacked archive is deployed with `-t dev` using the product dev identity, in `resource_group: product-dev`
- [x] The pipeline starts the product dev job, waits for it, and fails if the run fails

## Comments

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 keeps this artifact but changes where its parts come from: `deploy/` and the bundle would be rendered centrally at artifact build time, and the artifact must also record the platform version used, so a rollback rolls back platform code too.

**2026-11-04 (implementation):**
- `release-check` (`scripts/release.py check-tag`, `GIT_DEPTH: 0`): refuses tags that aren't valid GitLab generic package versions and commits not on the default branch (`git merge-base --is-ancestor`, tested with a local origin/clone).
- Package version rule, from GitLab's docs: `\A(\.?[\w+-]+\.?)+\z` (letters, digits, `_`, `+`, `-`, dot-separated; no `/`). Documented in `docs/ci-cd.md` and the README; recommended `vMAJOR.MINOR.PATCH`.
- `release-artifact`: `dbt deps`, then `release.py publish`: if `<product>/<tag>/<product>-<tag>.tar.gz` exists in the generic registry it is downloaded and reused, otherwise built and uploaded (`JOB-TOKEN`). Archive = tracked bundle/dbt files + installed `dbt_packages/` + `deploy/` + `scripts/publish_dbt_artifacts.py` + `RELEASE.json` (product, version, commit); deterministic bytes.
- `product-dev` (`resource_group: product-dev`, product dev identity): `release.py fetch` (never builds), `bundle deploy -t dev`, `bundle run -t dev dbt_build` (waits, fails on a failed run).
- Tests: `tests/test_release.py`, including the real HTTP client against a fake GitLab package API. **Not verified** in GitLab.
