# 07: Central platform repository for setup and deployment tooling (plan)

**What to build:** Split the template into two parts. Each data product repository owns its dbt code. One central **platform repository** owns the setup, dev-environment and deployment tooling. Teams get central fixes and improvements without re-cloning the template or editing their repo. Only breaking changes (a new major version) need a change in each repo.

**Blocked by:** None for the decisions. Implementation is best done after ci-cd#01–06, so the deployment tooling exists before it moves.

**Status:** needs-triage (a plan; the decisions below need confirming before it is split into tickets)

## For the agent picking this up

1. **Don't implement anything from this ticket while its status is `needs-triage`.** First go through "Open questions" and "Conflicts with earlier decisions" with the user, one at a time, and record each answer in `## Comments` at the bottom.
2. Once decided: write an ADR for the central platform repository (next free number in `docs/adr/`), update ADR 0002 (its "Under review" note), and add new terms to `GLOSSARY.md` (e.g. *platform repository*, *platform version*). Use "data product" and "product repo" as the glossary defines them.
3. Split "Proposed tickets" into numbered issue files (`08-…` onwards here, or a new `.scratch/platform-repo/` feature folder if the user prefers), each with `Blocked by:` lines. Then set this ticket to `Status: resolved` with a pointer to them.
4. Affected tickets already carry a "pending decision, dev-environment#07" comment: ci-cd#01, #03, #05, #07 and dev-environment#06. Both specs have a "Pending decision" section. Remove or update those notes when the decision is made.
5. The platform repo doesn't exist yet. Ask the user where it should live (GitLab group and name) before creating anything outside this repository.

### Current file → future home

| Today (this repo) | If accepted |
|---|---|
| `scripts/devenv.py`, `scripts/setup_dev.py`, `scripts/build_changed.py`, `tests/test_devenv.py`, `tests/test_build_changed.py` | platform repo: `dbtp` CLI and its tests |
| `macros/generate_schema_name.sql`, `macros/generate_alias_name.sql`, `macros/source_modes.sql` (incl. the `source()` override) | platform dbt package; one-line stubs stay in the product repo |
| `macros/personal_environment.sql`, `macros/assert_published_models_are_versioned.sql`, `macros/local_spark/` | platform dbt package (`on-run-start` calls the package macro; the `spark__` override needs a root stub, see `## Comments`) |
| `tests/test_macros.py` | platform repo integration tests |
| `local/` (compose, Dockerfile, metastore SQL, Spark config, `tpch.sql`) | platform repo, run through `dbtp local …` |
| `.devcontainer/Dockerfile` | platform image `…/dbt-platform:1` |
| `.devcontainer/devcontainer.json`, `.gitattributes` | stay (devcontainer.json points at the image) |
| `Makefile` | stays, reduced to forwarders (`setup: ; dbtp setup`) |
| `config/dev-environment.toml` | folded into the product repo's `platform.toml` (team values could later come from a central team registry) |
| `deploy/profiles.yml` | rendered centrally into the release artifact (ADR 0002 change) |
| `models/`, `dbt_project.yml`, `pyproject.toml`, `uv.lock`, `docs/published-interface.md` | stay in the product repo/template |

## The problem

Today a new product repo is a copy of this template. Everything is copied with the dbt code: `scripts/`, the macros, the Makefile, `local/`, `.devcontainer/`, and soon the CI pipeline and the bundle. After that, a fix (say, to `make clean-dev`'s matching or to the release pipeline) reaches each repo only when someone in that team copies it over by hand. Repos will drift, and the platform team can't tell which repo runs which version.

## What lives where

| Owned by the product repo (edited by the team) | Owned by the platform repo (consumed, never edited) |
|---|---|
| `models/`, `tests/`, seeds, snapshots, analyses | Setup and dev tooling: alias, `profiles.yml`, clone/clean, build-changed (today `scripts/`) |
| `dbt_project.yml` (name, layers, vars), source YAML | The dbt macros for schema naming, versioning, source modes, cleanup, local-Spark overrides (today `macros/`) |
| `platform.toml`: the product's settings (product name, team, catalogs, warehouse, schedule). The interface to the platform | Dev container image (today `.devcontainer/Dockerfile`) |
| `pyproject.toml` / `uv.lock`: dbt-core and dbt-databricks versions | Local Spark engine (today `local/`) |
| Small, stable stubs (below) | CI/CD pipeline jobs (ci-cd#03–06) |
| | Databricks Asset Bundle template and the deploy profile (ci-cd#01–02) |

Rule of thumb: if two products would have the same file, character for character, it belongs in the platform repo.

## How each piece is delivered

One platform repository, released with **one semantic version for everything** (`v1.4.2`). That avoids having to track which macro version works with which CLI or pipeline version. It publishes four artifacts per release:

1. **dbt package** (the macros), installed as a git package:
   ```yaml
   # packages.yml in the product repo
   packages:
     - git: "https://gitlab.example.com/<platform-group>/dbt-platform.git"
       subdirectory: dbt
       revision: "v1"          # moving major-version tag, see "Versions"
   ```
   dbt only uses some built-in overrides from the root project: `generate_schema_name`, `generate_alias_name`, `source()`. For those the product repo keeps one-line stubs, e.g. `{{ return(dbt_platform.generate_schema_name(custom_schema_name, node)) }}`. The `spark__` override needs a stub too (dbt's `dispatch` search order doesn't work for it, see `## Comments`). The stubs only change in a new major version.

2. **Platform CLI** (`dbtp`, a Python package; today's `scripts/`), with commands `setup`, `clone-sources`, `clean-dev`, `build-changed`, `local …`, `doctor`. The product repo's Makefile becomes a thin forwarder, so developers keep typing `make setup`:
   ```make
   setup: ; dbtp setup
   clean-dev: ; dbtp clean-dev
   ```

3. **Container image**, `registry.example.com/<platform-group>/dbt-platform:1`. It holds Python, uv, a pinned Databricks CLI and `dbtp`, and does two jobs:
   - The product repo's `devcontainer.json` only says `"image": "…/dbt-platform:1"` (plus mounts and the forwarded port).
   - CI uses the same image as its job image. Developers and pipelines therefore run identical tooling, and `dbtp` needs no separate install or registry login.

4. **GitLab CI/CD component**, used by the product repo's 5-line `.gitlab-ci.yml`:
   ```yaml
   include:
     - component: gitlab.example.com/<platform-group>/dbt-platform/dbt-product@1
       inputs:
         product: orders
   ```
   `@1` resolves to the newest 1.x release on every pipeline run. The component holds the MR, merge and release pipelines (ci-cd#03–06). It renders the bundle and the deploy profile from central templates plus `platform.toml` when the release artifact is built, so they freeze inside the artifact (ADR 0008).

## Versions: what updates automatically, and when

- **Minor and patch releases reach every repo with no commit there:**
  - CI resolves `@1` and `:1` on every run.
  - Developers get them when they rebuild their dev container. `dbtp doctor` (run by `make setup`, and as a warning in other commands) says when a newer 1.x image exists.
  - `dbt deps` pulls the latest `v1` tag on each run, because `package-lock.yml` stays uncommitted.
- **Prod stays reproducible.** The release pipeline records the platform version it used, and the release artifact freezes the rendered bundle, deploy profile and installed `dbt_packages/`. Rolling back an artifact rolls back the platform code with it.
- **Breaking changes:** a new major version (`v2`, `:2`, `@2`). Each repo moves when it chooses: bump three references and run `dbtp migrate`, which updates the stubs. Major versions should be rare and come with a migration note.
- **dbt-core and dbt-databricks versions** stay in each repo's `uv.lock`, because they affect model behaviour. The platform declares the supported range and `dbtp doctor` and CI fail outside it. Renovate (or a scheduled CI job) can open the bump MRs.

## Safety: changes that skip every product's review

A platform change reaches many products without their MRs, so the platform repo's own pipeline has to be the review:

- Integration tests against this template's sample product: `dbtp` commands, `dbt build` on the local Spark engine (`local/`), and a full MR/release dry run against a test product in the dev workspace.
- Protected tags. Only the platform team can release, and the moving `v1` tag is moved only by the release job.
- A changelog. Product teams can pin an exact version (`@1.4.2`, `revision: v1.4.2`) if they need to freeze, e.g. during a critical period.

## What this repository becomes

- The **platform repo** (new). It takes `scripts/`, `macros/`, `local/`, the dev container Dockerfile, and the CI/bundle work from ci-cd#01–06.
- A slimmed **product template** (this repo). It keeps the sample product, `platform.toml`, `packages.yml`, the stubs, the thin Makefile, `devcontainer.json` and `.gitlab-ci.yml`. Creating a repo from it stays a one-time copy, but almost nothing in the copy goes stale.

## Conflicts with earlier decisions

- **ADR 0002** has `deploy/profiles.yml` committed in each repo. Under this plan it is rendered centrally when the artifact is built. The rule that it is used only with `--profiles-dir deploy` and never at the repo root still holds. The ADR needs updating.
- **ci-cd#03** says "`.gitlab-ci.yml` only calls `make` targets; CI uses a standard Python image". Under this plan the jobs live in the central component and run the platform image.
- **ci-cd#07** (adoption guide) changes: adopting means creating a repo from the slim template, and the platform version policy needs documenting.
- **dev-environment#06** (dev container) splits: the image moves to the platform repo, and `devcontainer.json` stays.

## Proposed tickets (after triage)

1. Platform repo skeleton: one version, release job that moves `v1`/`:1`, changelog, protected tags.
2. Move the macros into the dbt package; root-project stubs and `dispatch` config in the template.
3. Move `scripts/` into the `dbtp` CLI; thin Makefile; `dbtp doctor` (version and dbt-range checks).
4. Platform image as dev container and CI image; `devcontainer.json` points at it.
5. CI/CD component with `platform.toml` inputs; bundle and deploy profile rendered into the release artifact (reworks ci-cd#01–06 and ADR 0002).
6. Platform integration tests against the sample product (local engine + dev workspace dry run).
7. `dbtp migrate` and the first major-version migration note (template v1 → platform v1).

## Open questions

- Does our GitLab instance and tier support the CI/CD catalog with partial-version ranges (`@1`)? If not, `include: project … ref: v1` with a moving branch or tag works the same way.
- Should `dbtp` also be installable without the image (e.g. `uvx` from the GitLab package registry) for people who don't use the dev container? That needs registry credentials on developer machines.
- Does git access to the platform repo work everywhere it's needed? Developers' `dbt deps` uses their git credentials; CI needs `CI_JOB_TOKEN` allowlisting on the platform project.
- How much of `platform.toml` is validated centrally, and which fields does it need (product name, team, catalogs, warehouse, schedule, notification targets)?
- Should a product repo be able to override platform behaviour at all (e.g. extra CI jobs, a custom schedule)? Proposal: only through `platform.toml` and the component's documented inputs.

## Comments

**2026-11-10, first step agreed with the user (in-repo only):** proposed ticket 3 ("Move `scripts/` into the `dbtp` CLI; thin Makefile") is done inside this repository, without deciding anything else here. The tooling is now the `dbtp` Python package in `tools/dbtp/` (own `pyproject.toml` and version, `dbtp` entry point), a uv workspace member that the root `pyproject.toml` depends on. Every Makefile recipe forwards to `dbtp`. The `clean-dev` confirmation, the local engine's compose orchestration, the offline `parse` and the bundle deploy guard moved from the Makefile into Python. dbtp imports nothing from the product repo and finds it at run time (`dbt_project.yml` upwards from cwd, or `--project-dir` / `$DBTP_PROJECT_DIR`), so it can move to its own repository by changing one `[tool.uv.sources]` entry. `.gitlab-ci.yml` is unchanged (it still calls `make`).

Not done: `dbtp doctor`, the platform repo itself, the macros package, the image, the CI component. All open questions above are still open. Two things this step settled that the later tickets should keep: the job's `publish_dbt_artifacts.py` stays a standalone file (Databricks SDK only) shipped in the artifact, and `ci_tools.py` stays standard-library Python, because both run where dbtp isn't installed.


**2026-11-10, second step agreed with the user (in-repo only):** proposed ticket 2 ("Move the macros into the dbt package") is done inside this repository. The macros are the `dbt_platform` dbt package in `tools/dbt_platform/` (own `dbt_project.yml` and version), installed from `packages.yml` with `local: tools/dbt_platform`; moving it out means replacing that entry with `git:` + `revision:`. The root project keeps one-line stubs in `macros/dbt_platform.sql` (`generate_schema_name`, `generate_alias_name`, `source`, `spark__alter_column_set_constraints`) and `on-run-start` calls `dbt_platform.assert_published_models_are_versioned()`. Things this step found that correct the plan above:

- **`dispatch` config does not cover the `spark__` override.** For namespace `dbt` dbt searches package by package and tries every adapter prefix inside each, so a search order of `[product, dbt_platform, dbt]` picks `dbt_platform.spark__alter_column_set_constraints` over dbt-databricks' `databricks__` one on Databricks. The same was already true of the root-project override on `main`: on Databricks it replaced dbt-databricks' macro and, given a model instead of a column dict, silently applied no NOT NULL constraints for enforced contracts. Now the package macro has a plain name, a root stub calls it, and it hands every adapter other than spark back to `<adapter>__alter_column_set_constraints`. `tests/test_macros.py` checks Databricks gets `SET NOT NULL`.
- Package macros must call each other with the `dbt_platform.` prefix; unprefixed calls fail when a root-project node is the caller.
- `dbt deps` installs a `local:` package as an absolute symlink. The release artifact now copies it (`installed_files` follows links), and `dbtp local dbt` runs `dbt deps` on the host and makes the link relative so it resolves in the container. `dbtp parse` and the `tests/` fixture run `dbt deps` first. With a `git:` package none of this is needed.

Not done: the platform repository, `dbtp doctor`, the image, the CI component. All open questions above are still open.
