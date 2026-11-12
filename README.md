# dbt on Databricks: data product template

A GitLab repository template for one **data product**: a dbt project on Databricks with

- a **personal environment** for every developer, in the team catalog, so nobody's `dbt build` touches a teammate's or a shared environment;
- a deployment pattern: MR builds, then GitLab releases that deploy one **release artifact** first to the **product dev catalog** (as the release's test) and, after a manual approval, to the **product prod catalog**.

Terms in bold are defined in [`GLOSSARY.md`](GLOSSARY.md). Decisions and their reasons are in [`docs/adr/`](docs/adr/). Every workflow, step by step with diagrams: [`docs/workflows.md`](docs/workflows.md).

> Status: the development tooling is verified offline and on the local Spark engine (the Databricks logins, `make clone-sources`, `make clean-dev` and `make build-changed` have not run on a workspace yet); the deployment is verified offline only (see [`docs/ci-cd.md`](docs/ci-cd.md), "Not verified yet"). Expect to fix small things on the first real run.

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

Create the repository from this template in GitLab (**New project → Create from template**), clone it and open it in the dev container ([`docs/dev-container.md`](docs/dev-container.md)). The template works as it is: its sample product, `sample_product`, has a source, models, a seed and tests that build without changes.

1. **Initialize the repository** with your data product name and the team's dev settings:

   ```sh
   uv run dbtp init
   ```

   It asks for the data product name (lowercase letters and digits joined by single underscores, no `__`; it is also the dbt project name), then the team's dev settings: the dev workspace's **server hostname**, the **SQL warehouse ID** of the team's shared warehouse, the team catalog and the product dev catalog. Then the deployment values for `databricks.yml`: the product dev job's SQL warehouse (default: the team warehouse) and identity, the prod workspace (default: the dev workspace; one workspace for everything works, since environments are picked by catalog), the product prod catalog, the prod SQL warehouse (default: the product dev warehouse) and identity, and the prod schedule (a Quartz cron expression). Workspaces and warehouses are asked for as the UI shows them: the server hostname is under **SQL Warehouses → your warehouse → Connection details** (e.g. `dbc-1234abcd-5678.cloud.databricks.com`; a workspace URL from the browser works too), and the SQL warehouse ID is shown next to the warehouse name (or paste the **HTTP path** from Connection details). Identities are the **application IDs** of the product's service principals; press Enter to leave them (and the catalogs) for later.

   It writes the name into every file that must repeat it (`dbt_project.yml`, `deploy/profiles.yml`, `databricks.yml`, `local/profiles.yml`), the dev settings into `config/dev-environment.toml`, and the deployment values into the `dev` and `prod` targets of `databricks.yml`, keeping the files' comments. At the end it lists every `<placeholder>` still left, with the option that fills it. Run it again to change any value (it shows the current ones); `uv run dbtp init --help` lists the options for running it without questions (`--yes`). `uv run dbtp bundle …` refuses a target that still has placeholders. Commit the result.
2. **Build the samples** to check that your environment works: `make setup`, `make build` (section 3). Then follow [`docs/first-models.md`](docs/first-models.md) to add your own models.
3. **Deployment settings:** the service principals, if you left them for later (`uv run dbtp init --product-dev-service-principal … --product-prod-service-principal … --yes`), and the GitLab settings (step 5).
4. **Sources and models:** add your sources and replace the sample models (`models/staging/sample/`, which generate their own rows) and the sample seed with your own, as [`docs/first-models.md`](docs/first-models.md) shows. Keep the layers (`staging`, `intermediate`, `published`, `seeds`). Published models have enforced contracts; see [`docs/published-interface.md`](docs/published-interface.md) for how to change them.
5. **GitLab settings** ([details](docs/ci-cd.md)):
   - CI/CD variables `DATABRICKS_OIDC_AUDIENCE`, `TEAM_CLIENT_ID`, `PRODUCT_DEV_CLIENT_ID`/`_SECRET` and `PRODUCT_PROD_CLIENT_ID`/`_SECRET`. Mark the product ones masked and protected.
   - Protected tags for release tags (e.g. `v*`), with a restricted list of who may create them.
   - On Premium or Ultimate, a protected environment `prod` with deployment approvals.
   - Under "Prevent outdated deployment jobs", allow job retries for rollback deployments.

## 3. Daily development

Work in the dev container (`.devcontainer/`, see [`docs/dev-container.md`](docs/dev-container.md)). New to the project? [`docs/first-models.md`](docs/first-models.md) takes you from the sample models to your own. Once:

```sh
make setup              # tools, Databricks login, your profiles.yml (asks for your developer alias), dbt deps
```

Then:

```sh
make clone-sources                # personal shallow clones of the sources (default source mode: clone)
make build                        # dbt build: build + test everything into your personal environment
make build SELECT=+customers      # part of the graph (also: make run, make test, make compile)
make build SOURCE_MODE=prod       # read prod sources directly for one run
uv run dbt show --select customers   # look at a model's rows
make build-changed                # deferred build: only what you changed; the rest from product dev
make lint parse                   # before you push: sqlfluff, yamllint, offline dbt parse
make clean-dev                    # drop your whole personal environment
make help                         # all targets
```

The dbt targets pass `ARGS="..."` on to dbt (`make build ARGS="--full-refresh"`); for anything else, run `uv run dbt …` directly, it uses the same profile.

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
| `models/`, `seeds/`, `macros/`, `dbt_project.yml`, `packages.yml` | The dbt project (`macros/` holds only the stubs dbt needs in the root project) |
| `tools/dbt_platform/` | The platform's dbt macros as a dbt package (schema naming, source modes, environment cleanup, local-Spark overrides), installed by `dbt deps` |
| `config/dev-environment.toml` | Team settings for personal environments |
| `databricks.yml`, `resources/` | The Databricks Asset Bundle (the job) |
| `deploy/profiles.yml` | Deployment profile, only used with `--profiles-dir deploy` |
| `.gitlab-ci.yml` | The pipelines (the `make` checks, and `uv run dbtp …` for the CI-only steps) |
| `Makefile`, `tools/dbtp/` | Tooling: the `dbtp` package (`uv run dbtp --help`), and a Makefile with the developer's daily commands (`make help`) |
| `local/` | The local Spark engine |
| `tests/` | Tests of the project's macros, bundle, deploy profile and artifact (`make test-tooling`, which also runs `tools/dbtp/tests/`) |
| `docs/` | Guides and ADRs |

The team owns the repository. The exception for now is the shared tooling, `tools/dbtp/` and `tools/dbt_platform/` (with the stubs in `macros/dbt_platform.sql`): the platform team maintains it and will move it into its own repository. Don't change it here; tell the platform team what you need.
