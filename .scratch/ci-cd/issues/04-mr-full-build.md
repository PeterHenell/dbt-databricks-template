# 04: MR full build

**What to build:** A passing MR means the code builds and its tests pass: every MR pipeline builds the whole project in the team catalog, using the team identity.

**Blocked by:** 03 (GitLab pipeline with static checks and Databricks login)

**Status:** ready-for-agent

- [ ] MR pipelines log in as the team identity
- [ ] Each MR build first drops the schemas `<product>__mr__*` in the team catalog, then runs a full `dbt build` (no `--defer`) into `<product>__mr__<layer>`
- [ ] MR builds read prod sources directly
- [ ] All MR builds share `resource_group: mr-build`, so only one runs at a time
- [ ] A failing model or test fails the MR pipeline
- [ ] The schema naming macro supports this MR target without a developer alias
- [ ] Using `--defer` against product dev to reduce cost is noted as a later improvement (see ADR 0009)
