# 05: `make build-changed` (deferred build)

**What to build:** A developer can build only the models they changed, with references to unchanged models resolved against the latest release candidate in product dev, instead of rebuilding the whole project.

**Blocked by:** 01 (Minimal end-to-end skeleton), ci-cd#02 (Job runs publish dbt artifacts)

**Status:** ready-for-agent

- [ ] `make build-changed` downloads `latest/manifest.json` from the product dev catalog's `_dbt_artifacts.state` volume using the developer's own login
- [ ] It runs `dbt build --select state:modified+ --defer --state <downloaded>` into the developer's personal environment
- [ ] Unchanged upstream models are read from the product dev catalog
- [ ] A clear error if no product dev manifest exists yet (no successful product dev run)
