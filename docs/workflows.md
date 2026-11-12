# Developer workflows

How the team works with this repository, from a new developer's first `uv run dbtp init` to rolling back prod. Each section has a short description and a PlantUML activity diagram:

- the **lanes** show where a step runs (you in the dev container, GitLab CI, or Databricks);
- each **box** is a step, with the command to type in `monospace`;
- the **note** next to it says what the step produces.

Names in the diagrams use the sample product `sample_product` and a developer alias `jodo`. Replace them with your own product name and alias. Terms in bold are defined in [`GLOSSARY.md`](../GLOSSARY.md).

> Status: the development tooling is verified offline and on the local Spark engine; the deployment is verified offline only. The diagrams describe the intended flow; see [`ci-cd.md`](ci-cd.md), "Not verified yet".

| # | Workflow | When |
|---|---|---|
| [0](#0-set-up-your-environment-and-run-dbt) | Set up your environment and run dbt | First day, new machine |
| [1](#1-develop-a-feature-up-to-a-merge-request) | Develop a feature up to a merge request | Every change |
| [2](#2-release-and-deploy) | Release and deploy | Shipping merged work to prod |
| [3](#3-make-a-breaking-change-to-the-published-interface) | Make a breaking change to the published interface | Changing a published column, type or grain |
| [4](#4-create-and-refresh-source-clones-and-samples) | Create and refresh source clones (and samples) | Stale or broken dev data |
| [5](#5-roll-back-a-broken-release) | Roll back a broken release | Prod is broken after a deploy |
| [6](#6-release-a-fix-that-is-not-on-main-hotfix) | Release a fix that is not on `main` (hotfix) | Exceptional; not supported by default |
| [7](#7-a-release-fails-in-product-dev) | A release fails in product dev | The release's test run fails |
| [8](#8-add-a-new-source) | Add a new source | New upstream data |
| [10](#10-try-a-change-on-the-local-engine-no-databricks) | Try a change on the local engine (no Databricks) | Offline, or Databricks unavailable |
| [11](#11-create-a-new-data-product-from-the-template) | Create a new data product from the template | Once per data product |

Where things live:

| Environment | Catalog / schemas | Written by |
|---|---|---|
| Personal environment | team catalog, `<product>__<alias>__<layer>` | you (your own login) |
| MR build | team catalog, `<product>__mr__<layer>` | the MR pipeline (team identity) |
| Product dev | product dev catalog, `<layer>` | the release pipeline (product dev identity) |
| Product prod | product prod catalog, `<layer>` | the prod job on its schedule (product prod identity) |

**Diagrams** are PlantUML code blocks in this page. GitLab draws them when PlantUML is enabled on the instance (it is on gitlab.com; on a self-managed GitLab an admin turns it on under **Admin → Settings → General → PlantUML**). Elsewhere, such as on GitHub, they show as source. To change a diagram, edit its block here.

In a diagram, `~` before `__` or `--` stops PlantUML from reading them as underline or strikethrough; it isn't shown in the rendered diagram.

---

## 0. Set up your environment and run dbt

You need: access to the dev workspace, and the team catalog (ask the platform team if not). Nothing else has to be set up by hand.

1. **Open the repository in the dev container** (VS Code: "Reopen in Container"). The container has the pinned uv, Databricks CLI and Python; see [`dev-container.md`](dev-container.md).
2. **Log in the Databricks CLI** with your own account. `dbtp init` uses this login to look up your name and later to download the product dev manifest.
3. **`uv run dbtp init`**: `uv run` installs the locked Python packages first. dbtp shows the repository settings (product name, team dev settings, deployment values), which the first developer filled in, and asks whether to change them: press Enter. Then it checks the login, suggests a **developer alias** (two letters of your first and last name), and writes the gitignored `./profiles.yml` with `schema: <product>__<alias>` in the team catalog. Then `dbt deps`.
4. **`make clone-sources`**: shallow clones of every source into your own `…__src_clone` schema. By default your builds read these, not prod.
5. **`make build`** (`dbt build`): builds and tests everything into your personal environment. The first dbt command opens a browser for dbt's own OAuth login.

Nothing you run can write outside `<product>__<alias>*`: the schema name always comes from your profile ([`generate_schema_name.sql`](../tools/dbt_platform/macros/generate_schema_name.sql) in the platform package). `make clean-dev` drops the whole environment when you want to start over.

```plantuml
@startuml workflow-0-setup
title 0. Set up your environment and run dbt

|Developer (dev container)|
start
:Clone the repository and open it in VS Code;
:**Reopen in Container**;
note right
  Dev container with pinned uv,
  Databricks CLI, Python
  (.devcontainer/)
end note
:""databricks auth login ~--host <dev-workspace-host>"";
note right
  Your CLI login (U2M OAuth),
  cached in the container
end note
:""uv run dbtp init"";
note right
  * ""uv run"": .venv with dbt, sqlfluff, ... (uv.lock)
  * repository settings: shown, kept (Enter)
  * alias suggested from your name, e.g. **jodo**
  * ./profiles.yml (gitignored):
    catalog = team catalog,
    schema = sample_product~__jodo
  * dbt_packages/ (""dbt deps"")
end note
:""make clone-sources"";
|Databricks (dev workspace)|
:Shallow clone of every source table;
note right
  sample_product~__jodo~__src_clone
  .crm~__customers, .crm~__orders, ...
  (no data copied)
end note
|Developer (dev container)|
:""make build"";
note right
  First run: browser OAuth login for dbt
end note
|Databricks (dev workspace)|
:Models built and tested on the team SQL warehouse;
note right
  sample_product~__jodo~__staging
  sample_product~__jodo~__intermediate
  sample_product~__jodo~__published
  target/ (manifest, run_results) locally
end note
|Developer (dev container)|
if (Start over?) then (yes)
  :""make clean-dev"";
  note right
    Lists sample_product~__jodo*,
    drops them after you type "yes"
  end note
else (no)
endif
stop
@enduml
```

---

## 1. Develop a feature up to a merge request

The inner loop runs in your personal environment; the MR pipeline is the gate. **A green MR means the coding is done** (ADR 0007): merging deploys nothing.

1. **Branch** from an up-to-date `main`.
2. **Change models** and build only what you need: `make build SELECT=<model>+` or `SELECT=+<model>` (`make run`, `make test` and `make compile` take the same options), or `make build-changed`, which builds only what you changed (`state:modified+`) and reads everything unchanged from product dev (needs a release in product dev first).
3. **Check before pushing**: `make lint parse` (sqlfluff, yamllint, offline `dbt parse` with the deploy profile) and, if you touched `tools/dbtp/`, macros, the bundle or CI, `make test-tooling`.
4. **Push and open a merge request.** The pipeline runs the static checks and then the **MR build**: it drops `<product>__mr__*` and builds the whole project into it from prod sources, as the team identity. MR builds run one at a time (`resource_group: mr-build`), so a second MR waits for the first.
5. **Review and merge.** The `main` pipeline runs the static checks again. Nothing is deployed.

```plantuml
@startuml workflow-1-feature
title 1. Develop a feature up to a merge request

|Developer (dev container)|
start
:""git switch main && git pull""
""git switch -c feature/<name>"";
repeat
  :Edit models/, macros/, YAML;
  if (Build what?) then (a model and its neighbours)
    :""make build SELECT=+customers+"";
  else (only what changed)
    :""make build-changed"";
    note right
      Downloads latest/manifest.json from
      /Volumes/<product_dev_catalog>/_dbt_artifacts/state
      to target/product-dev-state/, then
      ""dbt build ~--select state:modified+ ~--defer""
      Unchanged parents are read from product dev
    end note
  endif
  |Databricks (dev workspace)|
  :Build + tests in your personal environment;
  note right
    sample_product~__jodo~__<layer>
  end note
  |Developer (dev container)|
repeat while (Tests green and result looks right?) is (no)
->yes;
:""make lint parse"";
note right
  sqlfluff + yamllint;
  offline ""dbt parse"" with deploy/profiles.yml
end note
:""make test-tooling""  (if you changed tools/dbtp/, macros, bundle or CI);
:""git commit"" / ""git push -u origin feature/<name>""
Open a merge request;
|GitLab CI|
fork
  :lint, tooling-tests;
fork again
  :bundle-validate (team identity);
fork again
  :SAST, secret detection;
end fork
:mr-build  (""dbtp mr-build"", one MR at a time);
|Databricks (dev workspace)|
:Drop sample_product~__mr~__*;
:Full ""dbt build ~--target mr"" from prod sources;
note right
  sample_product~__mr~__staging, ~__intermediate,
  ~__published in the team catalog
  (overwritten by the next MR build)
end note
|GitLab CI|
if (Pipeline green?) then (yes)
  |Developer (dev container)|
  :Review, approve, **merge** to main;
  |GitLab CI|
  :main pipeline: static checks only;
  note right
    Nothing is deployed.
    main can be ahead of product dev and prod.
  end note
  stop
else (no)
  |Developer (dev container)|
  :Fix on the branch, push again;
  stop
endif
@enduml
```

---

## 2. Release and deploy

Releases deploy, merges don't (ADR 0007). A release is a GitLab release (and its tag) on a `main` commit; it can bundle several merged MRs. One **release artifact** is built per tag and promoted unchanged: first to product dev, where the job run is the release's test, then, after a manual step, to prod (ADR 0008).

1. **Create a GitLab release** on a `main` commit with a tag like `v1.4.0` (letters, digits, `.`, `_`, `+`, `-`; no `/`).
2. **`release-check`** refuses an invalid tag or a commit that isn't on `main`.
3. **`release-artifact`** builds `<product>-<tag>.tar.gz` (bundle, dbt project, installed packages, `RELEASE.json`) and stores it once in the package registry. A re-run reuses it.
4. **`product-dev`** deploys the artifact to product dev and runs the job. The job builds the whole project and then publishes `manifest.json` and `run_results.json` to the artifacts volume. If the run fails, the release stops here.
5. **`validate-prod`** validates the same artifact against the prod target.
6. **Approve and start `deploy-prod`** (manual). It deploys the same artifact to prod and does **not** start a run: the prod schedule builds the new version at its next run.

```plantuml
@startuml workflow-2-release
title 2. Release and deploy

|Release manager|
start
:GitLab: Deploy > Releases > **New release**
tag ""v1.4.0"" on a main commit;
|GitLab CI|
:release-check  (""dbtp release check-tag"");
note right
  Tag is a valid package version,
  its commit is on main
end note
:release-artifact  (""dbtp release publish"");
note right
  ""dbt deps"", then the archive
  **sample_product-v1.4.0.tar.gz**
  (databricks.yml, resources/, deploy/, models/,
  macros/, dbt_packages/, RELEASE.json)
  stored once in the package registry
end note
:product-dev  (""dbtp release fetch"", ""bundle deploy"", ""bundle run"")
as the product dev identity;
|Databricks (dev workspace)|
:""bundle deploy -t dev"";
note right
  Job "dbt_build" (no schedule),
  schema _dbt_artifacts, volume state
  in the product dev catalog
end note
:Job run: task dbt_build (""dbt build ~--target prod"");
note right
  staging, intermediate, published
  in the product dev catalog
end note
:Job run: task publish_dbt_artifacts;
note right
  /Volumes/<product_dev_catalog>/_dbt_artifacts/state/
    runs/<run_id>/manifest.json, run_results.json
    latest/  (what ""make build-changed"" uses)
end note
|GitLab CI|
if (Product dev run green?) then (no)
  :Pipeline fails, release stops;
  note right: See workflow 7
  stop
else (yes)
endif
:validate-prod  (""dbtp bundle validate -t prod"")
same archive, product prod identity;
|Release manager|
:Approve (Premium/Ultimate) and start **deploy-prod**;
|GitLab CI|
:deploy-prod  (""dbtp release fetch"", ""bundle deploy -t prod"");
|Databricks (prod workspace)|
:""bundle deploy -t prod"";
note right
  Job "dbt_build" with the cron schedule,
  updated to v1.4.0. **No run started.**
  GitLab environment "prod" shows v1.4.0
end note
:Next scheduled run builds v1.4.0;
note right
  Data in the product prod catalog,
  artifacts in its _dbt_artifacts.state volume
end note
stop
@enduml
```

---

## 3. Make a breaking change to the published interface

Consumers read the published interface from the `published` schema. A breaking change (removing or renaming a column, changing a type or the grain) is not stopped by any tool: it is a team decision, agreed with consumers before it is merged, and reviewers check MRs that touch `models/published/` for it (ADR 0010). There is no built-in versioning; if a product needs old and new side by side, see [`published-interface.md`](published-interface.md).

Non-breaking changes (a new column, a fix that keeps the contract) go through the normal feature flow.

```plantuml
@startuml workflow-3-breaking
title 3. Make a breaking change to the published interface

|Developer (dev container)|
start
:Find out who reads the published model;
:Agree the change and a date with its consumers;
note right
  Breaking: a column removed or renamed,
  a type or the grain changed.
  Nothing in the build stops it (ADR 0010):
  the team decides.
end note
:Branch from main (as in workflow 1);
:Change ""models/published/<model>.sql""
and its columns in ""_published.yml"";
:""make build SELECT=+<model>"";
|Databricks (dev workspace)|
:Model built against its new contract;
note right
  sample_product~__jodo~__published.<model>
end note
|Developer (dev container)|
:""make lint parse"", push, open MR
marked as a breaking change;
|GitLab CI|
:MR build: full build into ~__mr~__*;
|Developer (dev container)|
:Review checks the change and the
consumer agreement; merge;
:Release on the agreed date (workflow 2);
|Databricks (prod workspace)|
:Scheduled run builds the new contract
into ""published.<model>"";
stop
@enduml
```

---

## 4. Create and refresh source clones (and samples)

On personal targets, `source()` reads your own copies of the sources, not prod (ADR 0005). The variable `dev_source_mode` picks which copy:

| Mode | Reads | How to get it |
|---|---|---|
| `clone` (default) | `<product>__<alias>__src_clone.<source>__<table>` | `make clone-sources` |
| `prod` | the prod source directly | `--vars '{dev_source_mode: prod}'` for one run |
| `sample` | `…__src_sample` | **not implemented yet**: dbt stops with an error that says so |

Shallow clones copy no data; they reference the prod files at the moment of cloning, so they don't see newer prod data. Run `make clone-sources` again when you need fresher data, after you add a source, or when a clone breaks because prod ran `VACUUM` and removed files the clone still references. Views can't be shallow-cloned: the clone schema gets a view of the same name that reads prod. MR builds and deployed jobs always read prod; the mode is ignored there.

```plantuml
@startuml workflow-4-clones
title 4. Create and refresh source clones

|Developer (dev container)|
start
if (Why?) then (first time, new source,\nstale data, or\n"file not found" after prod VACUUM)
  :""make clone-sources"";
  |Databricks (dev workspace)|
  :Create schema sample_product~__jodo~__src_clone (if missing);
  :For each declared source;
  if (Source is a table?) then (yes)
    :""CREATE OR REPLACE TABLE ... SHALLOW CLONE <prod table>"";
    note right
      sample_product~__jodo~__src_clone.crm~__orders, ...
      Points at prod's current files, copies nothing
    end note
  else (view)
    :""CREATE OR REPLACE VIEW ... AS SELECT * FROM <prod view>"";
    note right: Always reads prod
  endif
  |Developer (dev container)|
  :Output: "Shallow-cloned N source table(s) ..."
  (fails if a source table doesn't exist in prod);
  :""uv run dbt build"";
  note right
    Default mode **clone**: staging models read
    sample_product~__jodo~__src_clone.*
  end note
else (one run against\ncurrent prod data)
  :""uv run dbt build ~--vars '{dev_source_mode: prod}'"";
  note right
    Reads prod sources directly;
    nothing is cloned
  end note
endif
|Databricks (dev workspace)|
:Models rebuilt in sample_product~__jodo~__<layer>;
note right
  ""dev_source_mode: sample"" is reserved:
  how samples are made is not decided yet
end note
stop
@enduml
```

---

## 5. Roll back a broken release

A rollback redeploys an earlier release's artifact: open that release's pipeline and re-run its `deploy-prod` job (ADR 0007). That brings back the earlier code and job definition. **Data is not rolled back**: the tables keep what the broken version wrote until the job runs again with the old code, at the next scheduled run or when you start it by hand.

This needs, once per project: "Allow job retries for rollback deployments" under Settings → CI/CD → General pipelines → "Prevent outdated deployment jobs", and the old release package must still be in the package registry (don't delete them).

Then fix forward: fix on `main` through an MR and make a new release.

```plantuml
@startuml workflow-5-rollback
title 5. Roll back a broken release (v1.5.0 -> v1.4.0)

|Release manager|
start
:Notice: v1.5.0 broke prod;
:GitLab: Operate > Environments > **prod**
(or the v1.4.0 release's pipeline);
:Re-run **deploy-prod** of ""v1.4.0"";
note right
  Needs "Allow job retries for
  rollback deployments" enabled
end note
|GitLab CI|
:deploy-prod  (""dbtp release fetch"", ""bundle deploy -t prod"");
note right
  Downloads the stored
  sample_product-v1.4.0.tar.gz
  (not rebuilt from today's code)
end note
|Databricks (prod workspace)|
:""bundle deploy -t prod"";
note right
  Job definition and code back to v1.4.0.
  GitLab environment "prod" shows v1.4.0.
  **Data still as v1.5.0 wrote it.**
end note
if (Can the data wait for the next scheduled run?) then (yes)
  :Next scheduled run rebuilds with v1.4.0;
else (no)
  |Release manager|
  :Start the prod job "dbt_build" by hand
  (Databricks UI: Jobs > Run now);
  |Databricks (prod workspace)|
  :Run rebuilds the data with v1.4.0;
endif
:Data back to v1.4.0's logic;
note right
  New _dbt_artifacts.state/runs/<run_id>/ and latest/
end note
|Developer (dev container)|
:Fix forward: branch, fix, MR (workflow 1);
:New release ""v1.5.1"" (workflow 2);
stop
@enduml
```

---

## 6. Release a fix that is not on `main` (hotfix)

**Not supported by default** (ADR 0007). The supported path is to fix forward on `main` and release, even when `main` has other merged changes: those changes passed their MR builds and the product dev run tests them again.

When you really can't release what's on `main`, the documented route is to branch from the release tag, fix, and tag a release on that branch. `release-check` refuses that tag on purpose (its commit is not on `main`), so a maintainer has to bypass the check deliberately. The fix must then be brought into `main`, or the next release brings the bug back. Everything after `release-check` is the normal release: the same artifact goes to product dev, is tested there, and then goes to prod.

```plantuml
@startuml workflow-6-hotfix
title 6. Release a fix that is not on main (hotfix, exceptional)

|Developer (dev container)|
start
if (Can main be released as it is?) then (yes, the default)
  :Fix on a feature branch, MR, merge (workflow 1);
  :Release from main, e.g. ""v1.5.1"" (workflow 2);
  stop
else (no, main holds unreleasable work)
endif
:""git switch -c hotfix/v1.5.1 v1.5.0"";
:Fix; ""uv run dbt build ~--select <changed>+""
in your personal environment;
:""git push"" the hotfix branch;
note right
  Optional: open an MR from the hotfix branch
  for review and an MR build
end note
|Maintainer|
:Decide to bypass the "tag is on main" rule
(e.g. temporarily change ""ci-release-check"");
note right
  Deliberate and visible in the history.
  Without it, release-check refuses the tag.
end note
:Create release ""v1.5.1"" on the hotfix branch commit;
|GitLab CI|
:release-artifact > product-dev (deploy + run)
> validate-prod > manual deploy-prod;
note right
  sample_product-v1.5.1.tar.gz built from
  the hotfix branch; tested in product dev
end note
|Databricks (prod workspace)|
:Prod job updated to v1.5.1;
|Maintainer|
:Undo the ""ci-release-check"" bypass;
|Developer (dev container)|
:Cherry-pick the fix into main via an MR;
note right
  Otherwise the next release from main
  brings the bug back
end note
stop
@enduml
```

---

## 7. A release fails in product dev

The product dev run is the release's test. When it fails, nothing reaches prod. The failed tag can't be "fixed": re-running its pipeline redeploys the same stored artifact. Fix on `main` and make a new release with a new tag. Product dev keeps the failed candidate deployed until then; `make build-changed` keeps using the manifest of the last **successful** run, because artifacts are only published after a green build.

```plantuml
@startuml workflow-7-failed-release
title 7. A release fails in product dev

|GitLab CI|
start
:product-dev job fails (v1.6.0);
|Databricks (dev workspace)|
note right
  Product dev catalog: partly built by v1.6.0.
  _dbt_artifacts.state/latest/ still from the
  last successful run (publish task didn't run)
end note
|Developer (dev container)|
:Read the failing dbt output
(GitLab job log, or the Databricks job run);
if (Transient? e.g. warehouse or network) then (yes)
  :Retry the product-dev job;
  note right
    Same stored archive, deployed and run again
  end note
  stop
else (no, a real bug)
endif
:Reproduce: ""uv run dbt build ~--select <failing model>+""
(maybe with ""~--vars '{dev_source_mode: prod}'"");
:Fix on a branch, MR, merge (workflow 1);
|Release manager|
:New release ""v1.6.1"" (workflow 2);
note right
  v1.6.0 is never deployed to prod.
  Its package stays in the registry.
end note
stop
@enduml
```

---

## 8. Add a new source

The source YAML names the source's prod location; every environment reads that, except personal environments, which read their clones. After adding the source, clone it before building in your environment (the default mode reads clones).

```plantuml
@startuml workflow-8-new-source
title 8. Add a new source

|Developer (dev container)|
start
:Ask the platform team for read access
from the dev workspace and from the job identities;
:Create ""models/staging/crm/_crm~__sources.yml""
with the prod catalog and schema
(database only when target.type == 'databricks');
:Add ""stg_crm~__<entity>.sql"" views;
:""make clone-sources"";
|Databricks (dev workspace)|
:Clone of the new tables;
note right
  sample_product~__jodo~__src_clone.crm~__<table>
end note
|Developer (dev container)|
:""uv run dbt build ~--select +stg_crm~__*"";
|Databricks (dev workspace)|
:Staging views on your clones;
note right
  sample_product~__jodo~__staging.stg_crm~__<entity>
end note
|Developer (dev container)|
:Add the table to ""local/sources.sql""
if the local engine should build it;
:""make lint parse"", MR (workflow 1);
|GitLab CI|
:MR build reads the new prod source;
note right
  Fails here if the team identity
  has no read access
end note
stop
@enduml
```

---

## 10. Try a change on the local engine (no Databricks)

`local/` runs the project on Apache Spark + Delta Lake in containers, through dbt-spark. Use it offline, or to try a change without a warehouse. Run these on the **host** (Podman or Docker, plus uv for `dbtp`), not in the dev container. There is no Unity Catalog locally, and a green local build doesn't replace a Databricks build.

```plantuml
@startuml workflow-10-local
title 10. Try a change on the local engine

|Developer (host shell)|
start
:""make local-sources"";
|Local containers|
:Build the dbt image, start Postgres (Hive metastore);
:Run local/sources.sql;
note right
  Small stand-in source tables
  in a local Spark warehouse
end note
|Developer (host shell)|
:""make local-dbt ARGS="run-operation clone_sources""" (optional);
note right
  sample_product~__local~__src_clone.*
  (LOCAL_ALIAS=... to change "local")
end note
repeat
  :Edit models;
  :""make local-dbt""  (or ""ARGS="build ~--select customers""");
  |Local containers|
  :dbt build with dbt-spark;
  note right
    sample_product~__local~__staging,
    ~__intermediate, ~__published
  end note
  |Developer (host shell)|
repeat while (Looks right?) is (no)
->yes;
:Inspect: ""make local-sql"";
:""make local-down"" (keeps data)
or ""make local-clean"" (deletes it);
:Continue on Databricks: workflow 1;
stop
@enduml
```

---

## 11. Create a new data product from the template

Once per data product. The full checklist is in [`README.md`](../README.md); this is its shape.

```plantuml
@startuml workflow-11-new-product
title 11. Create a new data product from the template

|Product team|
start
:Ask the platform team for: team catalog (if new),
product dev + prod catalogs, SQL warehouses,
3 service principals, OIDC policy (team identity),
OAuth secrets (product identities);
:GitLab: **New project from template**;
:Open it in the dev container;
:""uv run dbtp init"";
note right
  Sets the product name everywhere it is needed,
  config/dev-environment.toml and both targets
  of databricks.yml (warehouses, identities,
  prod workspace and catalog, schedule),
  then your profiles.yml and dbt deps
end note
:""make clone-sources build"";
note right
  The sample models, seed and tests
  build without any changes
end note
:Replace the samples with your own sources and models
(docs/first-models.md);
|GitLab settings|
:CI/CD variables: DATABRICKS_OIDC_AUDIENCE, TEAM_CLIENT_ID,
PRODUCT_DEV_CLIENT_ID/_SECRET, PRODUCT_PROD_CLIENT_ID/_SECRET
(product ones masked + protected);
:Protected tags ""v*"", protected environment ""prod""
with approvals (Premium/Ultimate),
allow job retries for rollback deployments;
|Product team|
:Each developer: workflow 0;
:First MR (workflow 1), first release (workflow 2);
note right
  After the first green product dev run,
  ""make build-changed"" works
end note
stop
@enduml
```
