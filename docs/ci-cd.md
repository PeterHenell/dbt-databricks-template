# Deployment and CI/CD

How this data product is deployed to Databricks and what the GitLab pipelines do. Decisions are in `docs/adr/0006`–`0009`; terms follow `GLOSSARY.md`.

**Status:** built and tested offline only (unit tests, `databricks bundle validate` against a fake workspace API, the static jobs in the CI image). It has not run against a real Databricks workspace or GitLab instance yet. See "Not verified yet" at the end.

## The pieces

| File | What it is |
|---|---|
| `databricks.yml` | The Databricks Asset Bundle. Targets `dev` (product dev catalog, dev workspace, no schedule) and `prod` (product prod catalog, prod workspace, cron schedule). The **only** place with environment-specific values (ADR 0008). |
| `resources/dbt_job.yml` | The one job: task `dbt_build`, then task `publish_dbt_artifacts`. Also the `_dbt_artifacts` schema and `state` volume. |
| `deploy/profiles.yml` | The deployment profile (ADR 0002). Target `prod` (the job) and target `mr` (MR builds). It holds no host, catalog, warehouse or secret: `DBT_HOST` and `DBT_ACCESS_TOKEN` come from the environment, catalog and warehouse from `--vars`. |
| `scripts/release.py` | Builds the release artifact, checks the release tag, stores and fetches the artifact in GitLab's package registry. |
| `scripts/mr_build.py` | The MR build. |
| `scripts/publish_dbt_artifacts.py` | Runs inside the job and publishes the dbt artifacts. |
| `scripts/install_ci_tools.sh` | Installs uv and the Databricks CLI in CI, at the versions pinned in `.devcontainer/Dockerfile`. |
| `.gitlab-ci.yml` | The pipelines. Every job only calls `make` targets. |

## The job

The job runs on serverless job compute, and the models run on the target's SQL warehouse. Its dbt task runs

```
dbt build --target prod --vars "{deploy_catalog: <catalog>, deploy_warehouse_id: <warehouse>}"
```

with `profiles_directory: deploy`. Databricks sets `DBT_HOST` and `DBT_ACCESS_TOKEN`, the token of the job's run-as identity. The job runs as the target's product identity (`run_as`), never as whoever deployed it. It never runs `dbt deps`, because the installed packages are part of the artifact.

The dbt and SDK versions in the job's environments must match `uv.lock`. `tests/test_bundle.py` fails if they differ. When you upgrade dbt, change both.

### dbt artifacts (ADR 0006)

After a successful `dbt_build`, the task `publish_dbt_artifacts` (default `run_if: ALL_SUCCESS`) copies `manifest.json` and `run_results.json` to

```
/Volumes/<catalog>/_dbt_artifacts/state/runs/<job_run_id>/
/Volumes/<catalog>/_dbt_artifacts/state/latest/
```

It writes `runs/` first, then `latest/`. A failed dbt task skips the publish task, so a failed run publishes nothing.

**Mechanism chosen: a follow-up task, not `--target-path` on the volume.** dbt writes `run_results.json` (and a manifest) even when the build fails, so writing straight to the volume would put failed runs into `latest/`. The follow-up task reads the dbt task's archived output, which Databricks keeps for every dbt task (`jobs get-run-output` → `dbt_output.artifacts_link`), and takes the files from its `target/` directory.

The bundle creates and owns the `_dbt_artifacts` schema and the `state` volume. If the schema already exists (for example, created by hand), the first deploy fails: drop the schema, or remove it from `resources/dbt_job.yml`.

## Make targets

```sh
make artifact [VERSION=local]          # dbt deps + build target/release/<product>-<version>.tar.gz, unpack to target/release/bundle/
make bundle-validate TARGET=dev|prod   # validate (from the repo; BUNDLE_DIR=target/release/bundle for the artifact)
make bundle-deploy TARGET=dev|prod     # deploy the unpacked artifact
make bundle-run TARGET=dev|prod        # start the job and wait; fails if the run fails
make lint parse                        # sqlfluff + yamllint, offline dbt parse with the deploy profile
```

Deploys always go from the unpacked artifact, so a hand deploy ships exactly what a release ships. To deploy and run in product dev by hand (needs `databricks auth login --host <dev workspace>` and permission to use the product dev identity):

```sh
make artifact bundle-deploy bundle-run TARGET=dev
```

Releases do this through the pipeline. Only do it by hand when the pipeline itself is broken, and don't deploy to prod by hand.

## Pipelines

| Pipeline | Jobs | Identity |
|---|---|---|
| Merge request | `lint` (sqlfluff, yamllint, `dbt parse`), `tooling-tests`, `bundle-validate` (target `dev`), `security-scan`, GitLab SAST and secret detection, then `mr-build` | team |
| `main` | The same static checks, without `mr-build`. **Nothing is deployed** (ADR 0007). | team |
| Release tag | `release-check` → `release-artifact` → `product-dev` → `validate-prod` → manual `deploy-prod` | product dev, then product prod |

### MR build (ADR 0009)

`make ci-mr-build` runs `scripts/mr_build.py`:

1. It takes the team's dev workspace, team catalog and warehouse from `config/dev-environment.toml`.
2. It gets an OAuth token for the CI login and hands it to dbt as `DBT_ACCESS_TOKEN`.
3. It drops `<product>__mr` and `<product>__mr__*` in the team catalog (macro `drop_mr_environment`, which refuses any target other than `mr`).
4. It runs a full `dbt build --target mr` (no `--defer`).

Sources are read from prod, as on every non-personal target. All MR builds share `resource_group: mr-build`, so only one runs at a time. A failing model or test fails the job and the MR.

*Later improvement:* defer to the product dev manifest (`--defer --state`) to rebuild only what changed (ADR 0009).

### Release

1. **Create a GitLab release** on a `main` commit. Creating the release creates its tag, which starts the pipeline.
2. **`release-check`** refuses the tag if it isn't a valid GitLab package version, or if its commit isn't on `main` (ADR 0007).
3. **`release-artifact`** builds the artifact and uploads it to the generic package registry: package `<product>`, version `<tag>`, file `<product>-<tag>.tar.gz`. If that file already exists, it is reused and nothing is rebuilt (written once, ADR 0008). The archive contains `RELEASE.json` with product, version and commit.
4. **`product-dev`** (`resource_group: product-dev`, environment `product-dev`) downloads that archive, runs `bundle deploy -t dev`, then `bundle run -t dev`. The job run is the release's test: if it fails, the pipeline fails.
5. **`validate-prod`** validates the same archive against `-t prod`, as the product prod identity.
6. **`deploy-prod`** (manual, environment `prod`, `resource_group: product-prod`) runs `bundle deploy -t prod` from the same archive. It does **not** start a run: the prod schedule takes over.

**Release tag names** must be valid GitLab generic package versions. GitLab checks them with `\A(\.?[\w+-]+\.?)+\z`: letters, digits, `_`, `+` and `-`, in parts joined by dots, with no `/` and no spaces. Use `vMAJOR.MINOR.PATCH` (e.g. `v1.4.0`). `release-check` enforces the rule (`scripts/release.py`, `tag_problem`).

Changing a release needs a new tag. Re-running the pipeline of an existing tag deploys the stored archive, even if you changed the code since.

### Approvals for `deploy-prod`

- **GitLab Premium or Ultimate:** make `prod` a protected environment (Settings → CI/CD → Protected environments) with deployment approvals and a list of who may deploy. By default the person who started the pipeline can't approve it.
- **Free tier** (no protected environments): limit `deploy-prod` to protected tags. Protect the release tags (e.g. `v*`, Settings → Repository → Protected tags), restrict who may create them, and mark the product identities' variables *protected*. GitLab only passes protected variables to pipelines of protected refs, so no other pipeline can log in as the product identities.

Do the protected-tag setup on every tier: the release pipeline's secrets depend on it.

### Rollback (ADR 0007)

Open the pipeline of the earlier release and re-run its `deploy-prod` job. That deploys the earlier archive, which brings back the earlier code and job definition. **Data is not rolled back.** The next scheduled run rebuilds it with the old code. Run the prod job by hand if that can't wait.

GitLab's "Prevent outdated deployment jobs" setting (Settings → CI/CD → General pipelines) blocks re-running an older deployment job unless **"Allow job retries for rollback deployments"** is also enabled. Enable it.

Don't delete release packages from the package registry: a rollback re-downloads them.

### Hotfixes (documented, not supported)

See ADR 0007. Branch from the release tag, fix, and tag a release on that branch. `release-check` refuses the tag because the commit isn't on `main`, so a maintainer has to bypass that check deliberately (e.g. by running the pipeline with a temporarily changed `ci-release-check`). Then cherry-pick the fix into `main`, or the next release brings the bug back. The default is to fix forward on `main` and release.

## Logging in to Databricks

There are three identities (Databricks service principals), one per pipeline:

| Identity | Used by | Needs |
|---|---|---|
| Team identity | MR and `main` pipelines | In the dev workspace: create and drop schemas in the team catalog, use the team's SQL warehouse, read the prod sources |
| Product dev identity | `product-dev` | In the dev workspace: deploy bundles, own the job; write the product dev catalog (incl. creating `_dbt_artifacts`), use the product dev warehouse, read the prod sources |
| Product prod identity | `validate-prod`, `deploy-prod` | The same in the prod workspace and product prod catalog |

The job runs as the product identity of its target (`run_as` in `databricks.yml`), so the deploying identity must also have the *Service Principal User* role on it. When the deployer and the run-as identity are the same, that is automatic.

### OIDC workload identity federation (team identity)

Databricks accepts GitLab as a workload identity provider ([Databricks docs: GitLab CI/CD](https://docs.databricks.com/aws/en/dev-tools/auth/provider-gitlab)). The job asks GitLab for an ID token (`id_tokens: DATABRICKS_OIDC_TOKEN` in `.gitlab-ci.yml`), and the Databricks CLI and SDK exchange it for a short-lived Databricks token (`DATABRICKS_AUTH_TYPE=env-oidc`, `DATABRICKS_CLIENT_ID`). No secret is stored.

The platform team creates a federation policy on the service principal (account console, or `databricks account service-principal-federation-policy create <sp-numeric-id> --json …`):

```json
{
  "oidc_policy": {
    "issuer": "https://<your-gitlab-host>",
    "audiences": ["<databricks-account-id>"],
    "subject_claim": "project_path",
    "subject": "<group>/<project>"
  }
}
```

- `issuer` is the `iss` claim of GitLab's tokens, i.e. your GitLab instance URL (`CI_SERVER_URL`, e.g. `https://gitlab.com`).
- `audiences` must contain the value of the CI variable `DATABRICKS_OIDC_AUDIENCE`. Databricks recommends your account ID.
- **Why `project_path` and not the default `sub`:** Databricks compares the subject *exactly*. GitLab's `sub` is `project_path:<group>/<project>:ref_type:<branch|tag>:ref:<name>`, so it changes with every MR branch. With `project_path`, any pipeline of this project can use the team identity. That's acceptable, because the team identity can do no more than a developer of the team.

### Client ID and secret (product identities, and the fallback)

The product identities can't use the same trick safely. Release pipelines run on tags, and every release has a new tag, so `sub` never matches one policy. `project_path` would let any pipeline of the project, including an MR from any branch that edits `.gitlab-ci.yml`, log in as product prod. So by default the product identities log in with an OAuth client ID and secret (`oauth-m2m`):

- `PRODUCT_DEV_CLIENT_ID` / `PRODUCT_DEV_CLIENT_SECRET` and `PRODUCT_PROD_CLIENT_ID` / `PRODUCT_PROD_CLIENT_SECRET` as CI/CD variables, **masked and protected**, with protected release tags (see "Approvals").

Any identity can switch login type through the project CI/CD variables `TEAM_AUTH_TYPE`, `PRODUCT_DEV_AUTH_TYPE` and `PRODUCT_PROD_AUTH_TYPE` (`env-oidc` or `oauth-m2m`), with `<ID>_CLIENT_ID` and, for `oauth-m2m`, `<ID>_CLIENT_SECRET`. That's also the fallback for the team identity if OIDC federation isn't available.

## Security scans

`.gitlab-ci.yml` includes GitLab's SAST and secret detection templates, which are available on every tier. Dependency scanning needs Ultimate; add `Jobs/Dependency-Scanning.gitlab-ci.yml` if you have it. `make security-scan` is a placeholder for any other scanner.

## Testing without Databricks

`make test-tooling` covers the deployment code offline:

- `tests/test_bundle.py`:
  - consistency checks (bundle name = product, pins = `uv.lock`, `dev` target = `config/dev-environment.toml`, only `prod` scheduled, CI jobs only call `make`);
  - schema names of both deploy-profile targets (`dbt ls`);
  - `databricks bundle validate` for `dev` and `prod` against a fake workspace API (`tests/mock_databricks.py`) on a copy with the placeholders filled in. That test is skipped if the CLI isn't installed.
- `tests/test_release.py`: tag rule, artifact contents and reproducibility, write-once logic against a fake GitLab package API, the "on `main`" check.
- `tests/test_publish_dbt_artifacts.py`, `tests/test_mr_build.py`: with fake SDK clients.
- `tests/test_macros.py`: `drop_mr_environment` (only `<product>__mr*`, refuses other targets).

## Not verified yet

These were checked only against documentation or a fake, and need a first real run:

- **The whole deploy and run** in a real workspace: `bundle deploy`, the serverless environment (`environment_version: "4"`), and that `profiles_directory: deploy` gets `DBT_HOST`/`DBT_ACCESS_TOKEN`. Databricks' own `dbt-sql` bundle template relies on both variables, but Databricks' dbt-task docs mention only `DBT_ACCESS_TOKEN`.
- **`publish_dbt_artifacts`:** that `{{job.run_id}}` is substituted in `spark_python_task` parameters, and the layout of the `artifacts_link` archive. The script searches for `target/manifest.json` instead of assuming a path.
- **Bundle-owned schema and volume:** the permissions the product identities need for them.
- **OIDC:** the `project_path` subject claim for GitLab (the Databricks docs only show the default `sub`), and the `issuer` value for a self-managed GitLab.
- **GitLab:** `id_tokens` `aud` from a CI variable, the registry upload with `CI_JOB_TOKEN`, `resource_group` behaviour, protected environments on your tier.
- **The MR build** against a real team catalog (`make ci-mr-build`).
