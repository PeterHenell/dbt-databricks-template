# Spec: CI/CD (first version)

Status: needs-triage

Result of the second grilling session on 2026-11-04. Terms follow `GLOSSARY.md`; reasoning is in `docs/adr/0006`–`0009`. Goal of the first version: a working release and deploy workflow. Data contracts and breaking-change checks are out of scope.

## Repository and tools

- The real repositories live in GitLab. All logic is in `make` targets, and `.gitlab-ci.yml` only calls them.
- CI uses a standard Python image, installs tools from the `uv` lockfile (cached), and uses a pinned Databricks CLI version. A custom image can come later if pipelines get too slow.
- Deployment uses Databricks Asset Bundles: one job with a dbt task, and targets `dev` (product dev catalog) and `prod` (product prod catalog).
- GitLab logs in to Databricks with OIDC workload identity federation. The documented fallback is an OAuth client ID and secret in masked, protected CI variables.

## Identities

| Pipeline | Identity | Writes to |
|---|---|---|
| MR | team identity | team catalog, `<product>__mr__*` |
| Release → product dev | product dev identity | product dev catalog |
| Release → prod | product prod identity | product prod catalog |

## MR pipeline

1. Lint, bundle validation, and security scans where available.
2. Drop `<product>__mr__*` in the team catalog, then run a full `dbt build` (no `--defer`) into `<product>__mr__<layer>`, reading prod sources directly.
3. All MR builds share `resource_group: mr-build`, so one runs at a time. The schemas are permanent; no GitLab environment or stop action.

A passing MR means the coding is done.

## Merge to `main`

Static checks only (lint, bundle validation, security scans). Nothing is deployed.

## Release pipeline

Started by a GitLab release created by hand (which creates its tag). Several merged MRs can go in one release. Tag names are chosen by hand for now.

1. Refuse unless the tagged commit is on `main`.
2. Build the artifact: bundle + dbt project + installed `dbt_packages/` + `deploy/profiles.yml`, with no environment-specific values. Upload it to the generic package registry as package `<product>`, version `<tag>`, file `<product>-<tag>.tar.gz`. It's written once; a re-run reuses the existing artifact.
3. `databricks bundle deploy -t dev` from the unpacked artifact, using the product dev identity (`resource_group: product-dev`).
4. Start the product dev job and wait for it. Its `dbt build` and tests are the gate.
5. Validate the bundle against the `prod` target.
6. Manual `deploy-prod` job in GitLab environment `prod` (`resource_group: product-prod`): `databricks bundle deploy -t prod` from the same artifact, using the product prod identity. **No run is started**; the prod schedule takes over. Use GitLab deployment approvals if the GitLab tier supports them.

## Jobs

- Schedules are set per bundle target: none for `dev` (runs only from release pipelines), cron for `prod`.
- Each successful run publishes `manifest.json` and `run_results.json` to `<catalog>._dbt_artifacts.state` under `latest/` and `runs/<run_id>/`. A failed run publishes nothing.
- The prod profile is `deploy/profiles.yml`, used with `--profiles-dir deploy`.

## Rollback and hotfixes

- Rollback: re-run an earlier release's `deploy-prod` job. Code and job definition go back; data does not and is rebuilt by the next scheduled run.
- Hotfixes are possible but not a supported path; see ADR 0007. Documented only.

## To verify when building (results, 2026-11-04, from docs and offline tests; see `docs/ci-cd.md`)

- `target/` of the dbt task: neither. A follow-up task reads the dbt task's archived output (`dbt_output.artifacts_link`), because dbt writes `run_results.json` even on failure (ci-cd#02).
- GitLab as issuer: yes (`env-oidc`). But Databricks matches the subject exactly and GitLab's `sub` contains the ref, so only the team identity uses OIDC (`subject_claim: project_path`); the product identities default to the client-secret fallback with protected tags (ci-cd#03).
- Package versions: `\A(\.?[\w+-]+\.?)+\z`; release tags like `v1.4.0` (ci-cd#05).
- Deployment approvals and protected environments: Premium/Ultimate. Free tier: protected tags and protected variables (ci-cd#06). Our tier is still to be confirmed.

## Deferred

- `--defer` in MR builds against the product dev manifest, to reduce rebuild costs.
- Data contracts (ODCS generated from manifests), breaking-change checks against prod, publishing to Collibra.
- How data product versions (releases) and contract versions are managed.

## Pending decision: central platform repository

`.scratch/dev-environment/issues/07-central-platform-repository.md` (status `needs-triage`) proposes moving the setup, dev-environment and deployment tooling into a central, versioned platform repository, so product repos keep only their dbt code. If accepted, it changes parts of this spec. That ticket lists the conflicts and open questions; resolve them with the user before implementing the affected parts.
