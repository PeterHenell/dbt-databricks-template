# 05: Release pipeline: artifact and test in product dev

**What to build:** Creating a GitLab release on a `main` commit packages the project once, deploys that package to product dev, and runs it there as the release's test.

**Blocked by:** 01 (Bundle deployable to product dev by hand), 03 (GitLab pipeline with static checks and Databricks login)

**Status:** ready-for-agent

- [ ] The pipeline runs on release tags only, and refuses a tag whose commit is not on `main`
- [ ] It builds one archive containing the bundle, the dbt project, installed `dbt_packages/` and `deploy/`, with no environment-specific values
- [ ] The archive is uploaded to the GitLab generic package registry as package `<product>`, version `<tag>`, file `<product>-<tag>.tar.gz`
- [ ] The artifact is written once: re-running the pipeline reuses the existing archive instead of rebuilding it
- [ ] Which characters GitLab allows in package versions is checked, and the rule for release tag names is documented
- [ ] The unpacked archive is deployed with `-t dev` using the product dev identity, in `resource_group: product-dev`
- [ ] The pipeline starts the product dev job, waits for it, and fails if the run fails
