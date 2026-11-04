# 06: Release pipeline: manual deploy to prod

**What to build:** After a release has passed in product dev, someone can approve it and the same package is deployed to prod; the prod schedule then picks it up.

**Blocked by:** 05 (Release pipeline: artifact and test in product dev)

**Status:** done (rollback not yet shown in a real pipeline)

- [x] After the product dev run succeeds, the bundle is validated against the `prod` target
- [x] A manual `deploy-prod` job in GitLab environment `prod` deploys the *same* archive with `-t prod`, using the product prod identity, in `resource_group: product-prod`
- [x] `deploy-prod` does not start a job run; the prod cron schedule in the bundle takes over
- [x] Whether the GitLab tier has protected environments with deployment approvals is checked; if yes, they are used, and if not, the manual job is limited to protected tags
- [ ] Rollback works by re-running an earlier release's `deploy-prod` job, which is shown and documented, including that data is not rolled back (see ADR 0007)

## Comments

**2026-11-04 (implementation):**
- `validate-prod` (needs `product-dev`): `bundle validate -t prod` from the fetched artifact, as the product prod identity.
- `deploy-prod`: `when: manual`, environment `prod`, `resource_group: product-prod`, fetches the same archive and runs `bundle deploy -t prod`; no run (tested: no `bundle-run`).
- Tier check (GitLab docs): protected environments and deployment approvals are Premium/Ultimate. Documented both: Premium → protected environment with approvals; Free → protected release tags + protected product-identity variables (only protected refs get them). Which tier we have is still to be confirmed.
- Rollback documented in `docs/ci-cd.md` and the README (re-run an earlier release's `deploy-prod`; data not rolled back; enable "Allow job retries for rollback deployments" when "Prevent outdated deployment jobs" is on). **Not yet shown** in a real pipeline (criterion left open).
