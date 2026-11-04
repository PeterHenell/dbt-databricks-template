# Releases, not merges, deploy: product dev holds the release candidate

A passing MR means the coding work is done; merging to `main` runs only static checks and deploys nothing. Deployments start from a GitLab release created by hand on a `main` commit, which may include several merged MRs. The release pipeline deploys to the product dev catalog, runs the job there as its test, and then waits for a manual `deploy-prod`. So product dev holds the latest release candidate, and prod holds the latest approved release; `main` can be ahead of both.

## Considered Options

- **Continuous deployment (`main` = prod)**: rejected; every merge would deploy to prod, with no batching and no control over timing.
- **Merges deploy to product dev, releases deploy to prod**: rejected; product dev would run on every merge, and a release tagged on an older commit would roll product dev back.
- **A long-lived `production` branch updated by release MRs**: rejected; it adds a second long-lived branch and back-merges, for the benefit of having prod's code on a branch.
- **Deploy from the MR, then merge**: rejected; no batching, and "coding done" would only come after the prod deploy.

## Consequences

- Rollback means re-running an earlier release's `deploy-prod` job. Code and job definition go back; data does not and is rebuilt by the next scheduled run.
- Hotfixes are possible but not a supported path. One can branch from the release tag, fix, and tag a release from that branch. The release pipeline's "commit must be on `main`" check then has to be relaxed, and the fix must be cherry-picked back into `main` by hand, or the next release brings the bug back. The default is to fix forward on `main` and release.
