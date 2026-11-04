# dbt on Databricks: data product template

A GitLab repository template for one **data product**: a dbt project on Databricks with

- a **personal environment** for every developer, in the team catalog, so nobody's `dbt build` touches a teammate's or a shared environment;
- a deployment pattern: MR builds, then GitLab releases that deploy one **release artifact** first to the **product dev catalog** (as the release's test) and, after a manual approval, to the **product prod catalog**.

Terms in bold are defined in [`GLOSSARY.md`](GLOSSARY.md). Decisions and their reasons are in [`docs/adr/`](docs/adr/).

> Status: the development tooling is verified offline and on the local Spark engine; the deployment is verified offline only (see [`docs/ci-cd.md`](docs/ci-cd.md), "Not verified yet"). Expect to fix small things on the first real run.

## 1. Ask the platform team for these

| What | Used for |
|---|---|
| **Team catalog** in the **dev workspace** (if your team doesn't have one yet) | Personal environments (`<product>__<alias>__*`) and MR builds (`<product>__mr__*`) |
| **Product dev catalog** (dev workspace) and **product prod catalog** (prod workspace) for the new data product | The deployed data product |
| Read access from the dev workspace to the prod catalogs that hold your sources | Developers and MR builds read prod sources |
| The team's shared SQL warehouse in the dev workspace, and a SQL warehouse for the job in each of product dev and prod | Running the models |
| Three service principals: the **team identity**, the product dev identity and the product prod identity (the **product identities**), with the grants in [`docs/ci-cd.md`](docs/ci-cd.md#logging-in-to-databricks) | MR pipeline, release to product dev, release to prod |
| An OIDC federation policy for the team identity (GitLab as issuer), and OAuth secrets for the product identities | GitLab logging in to Databricks ([details](docs/ci-cd.md#logging-in-to-databricks)) |

## 2. Turn the template into your data product

Create the repository from this template in GitLab, then:

1. **Name the product.** The data product name is the dbt project name: lowercase letters and digits joined by single underscores (no `__`). Replace `sample_product` with it in:
   - `dbt_project.yml`: both `name` and `profile`, and the model block `models: sample_product:`;
   - `deploy/profiles.yml`: the top-level key, and the `mr` target's `schema: <product>__mr`;
   - `databricks.yml`: `bundle.name`;
   - `local/profiles.yml`: the top-level key.

   Also change `name` in `pyproject.toml` if you like. `make setup` and `make test-tooling` fail if these names don't match.
2. **Team settings:** fill in `config/dev-environment.toml` (dev workspace host, team SQL warehouse, team catalog, product dev catalog).
3. **Deployment settings:** fill in the `<placeholders>` of both targets in `databricks.yml`: workspace host, product catalog, SQL warehouse, product identity (application ID). The `dev` target must use the same host and product dev catalog as `config/dev-environment.toml`. Set the prod schedule (`variables.schedule`, a Quartz cron expression).
4. **Sources:** replace the sample `tpch` source (`models/staging/tpch/`, the `tpch_*` vars in `dbt_project.yml`, `local/tpch.sql`) with your real sources. Keep the locations in variables.
5. **Models:** replace the sample models. Keep the layers (`staging`, `intermediate`, `published`). Every published model is versioned; see [`docs/published-interface.md`](docs/published-interface.md).
6. **GitLab settings** ([details](docs/ci-cd.md)):
   - CI/CD variables `DATABRICKS_OIDC_AUDIENCE`, `TEAM_CLIENT_ID`, `PRODUCT_DEV_CLIENT_ID`/`_SECRET` and `PRODUCT_PROD_CLIENT_ID`/`_SECRET`. Mark the product ones masked and protected.
   - Protected tags for release tags (e.g. `v*`), with a restricted list of who may create them.
   - On Premium or Ultimate, a protected environment `prod` with deployment approvals.
   - Under "Prevent outdated deployment jobs", allow job retries for rollback deployments.

## 3. Daily development

Work in the dev container (`.devcontainer/`, see [`docs/dev-container.md`](docs/dev-container.md)). Once:

```sh
make setup              # tools, Databricks login, your profiles.yml (asks for your developer alias), dbt deps
```

Then:

```sh
make clone-sources                         # personal shallow clones of the sources (default source mode: clone)
uv run dbt build                           # build + test into your personal environment
uv run dbt build --select +customers       # part of the graph
uv run dbt build --vars '{dev_source_mode: prod}'   # read prod sources directly for one run
make build-changed                         # deferred build: only what you changed; the rest from product dev
make clean-dev                             # drop your whole personal environment
```

- Your personal environment is the set of schemas `<product>__<alias>__<layer>` in the team catalog. Nothing you run can write anywhere else.
- **Source modes:** `clone` (default) reads your shallow clones, `prod` reads prod directly. Run `make clone-sources` again when prod data has moved on, or when a clone breaks after a prod `VACUUM`.
- `make build-changed` needs a release in product dev first: it defers to the manifest published by the last successful product dev run.
- No Databricks at hand: `make local-sources local-dbt` runs the project on a local Spark engine (on the host, not in the dev container).

## 4. From change to prod

1. **Merge request.** The pipeline runs lint (SQL, YAML), `dbt parse`, the tooling tests, bundle validation and security scans. Then the **MR build**: a full `dbt build` into `<product>__mr__*` in the team catalog, as the team identity. MR builds wait for each other. **A green MR means the coding is done.**
2. **Merge to `main`.** Static checks only. Nothing is deployed.
3. **Create a GitLab release** on a `main` commit, with a tag like `v1.4.0`. Letters, digits, `.`, `_`, `+` and `-` only, since the tag becomes the package version. One release can bundle several merged MRs. The release pipeline then:
   1. refuses the tag if its commit isn't on `main`;
   2. builds the release artifact once and stores it in the package registry as `<product>-<tag>.tar.gz`;
   3. deploys it to product dev and runs the job there. **That run is the release's test**; if it fails, the release stops;
   4. validates the same artifact against prod.
4. **Approve and run `deploy-prod`** (manual job, environment `prod`). It deploys the same artifact to prod. No run is started: the prod schedule builds it at its next run.

Product dev always holds the latest release candidate and prod the latest approved release; `main` can be ahead of both (ADR 0007).

## 5. When something goes wrong

- **Rollback:** open an earlier release's pipeline and re-run its `deploy-prod`. Code and job definition go back. **Data does not**: the next scheduled run rebuilds it, or start the prod job by hand.
- **Hotfix:** not a supported path. Fix forward on `main` and make a new release. If you really must, ADR 0007 and [`docs/ci-cd.md`](docs/ci-cd.md#hotfixes-documented-not-supported) describe the route and its risks.
- **Failed release in product dev:** fix on `main` via an MR, then make a new release (a new tag). Re-running the old pipeline redeploys the same stored artifact.

## Repository map

| Path | What |
|---|---|
| `models/`, `macros/`, `dbt_project.yml` | The dbt project |
| `config/dev-environment.toml` | Team settings for personal environments |
| `databricks.yml`, `resources/` | The Databricks Asset Bundle (the job) |
| `deploy/profiles.yml` | Deployment profile, only used with `--profiles-dir deploy` |
| `.gitlab-ci.yml` | The pipelines (they only call `make` targets) |
| `Makefile`, `scripts/` | Developer and CI tooling (`make help`) |
| `local/` | The local Spark engine |
| `tests/` | Tests of the tooling (`make test-tooling`) |
| `docs/` | Guides and ADRs |
