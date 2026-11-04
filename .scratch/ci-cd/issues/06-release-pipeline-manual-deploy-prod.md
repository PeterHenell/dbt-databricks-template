# 06: Release pipeline: manual deploy to prod

**What to build:** After a release has passed in product dev, someone can approve it and the same package is deployed to prod; the prod schedule then picks it up.

**Blocked by:** 05 (Release pipeline: artifact and test in product dev)

**Status:** ready-for-agent

- [ ] After the product dev run succeeds, the bundle is validated against the `prod` target
- [ ] A manual `deploy-prod` job in GitLab environment `prod` deploys the *same* archive with `-t prod`, using the product prod identity, in `resource_group: product-prod`
- [ ] `deploy-prod` does not start a job run; the prod cron schedule in the bundle takes over
- [ ] Whether the GitLab tier has protected environments with deployment approvals is checked; if yes, they are used, and if not, the manual job is limited to protected tags
- [ ] Rollback works by re-running an earlier release's `deploy-prod` job, which is shown and documented, including that data is not rolled back (see ADR 0007)
