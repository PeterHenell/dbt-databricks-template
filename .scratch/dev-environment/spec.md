# Spec: personal development environments

Status: needs-triage

Result of the grilling session on 2026-11-04. Terms follow `GLOSSARY.md`; the reasoning behind each choice is in `docs/adr/0001`–`0005` (and `0006` for where dbt artifacts are published).

## Platform assumptions

- Unity Catalog only; no `hive_metastore` support.
- One metastore, two workspaces: dev and prod.
- Dev workspace: one team catalog per team (personal environments live here) and one product dev catalog per data product (CI deploys here). Prod workspace: one product prod catalog per data product.
- Identities: one per team (team catalog), and one per data product per environment (product dev, product prod).
- The real repositories live in GitLab; this GitHub repo is a placeholder.
- The dev workspace has read-only access to prod catalogs.
- Teammates can read each other's personal environments by default; the platform team grants this, not the template.

## Project shape

- One repository = one data product. The product name is a single project variable and sets both the product catalog and the personal environment prefix.
- Prod schemas: `staging`, `intermediate`, `v1`, `v2`, … (one per active contract version), and the internal `_dbt_artifacts`.
- Published models use dbt model versions; version N is built into schema `vN` under the model's plain name. Older versions are built until their `deprecation_date`.
- Enforced dbt model contracts on every published model.
- SQL models only. The structure must leave room for Python models later (they need cluster or serverless job compute, not the SQL warehouse).

## Developer setup (`make setup`)

- Developers run dbt locally. The Python toolchain is pinned (e.g. `uv` with a lockfile).
- Developers may use macOS, Linux or Windows: the toolkit runs in a Docker-based dev container (`.devcontainer/`), so the Makefile and scripts only have to work in one Linux environment (ticket 06).
- Authentication is OAuth user-to-machine (`auth_type: oauth`) through the Databricks CLI login.
- Compute is one shared serverless SQL warehouse for dev.
- Setup suggests a developer alias: the first 2 letters of the first name plus the first 2 of the last name (`Peter Henell` → `pehe`), with non-ASCII letters converted (`Åsa Öberg` → `asob`). The developer can accept or change it.
- Setup writes a gitignored `profiles.yml` at the repo root. It has profile name = product name, target `dev`, the team catalog, the shared warehouse, and `schema: <product>__<alias>`.
- Alias collisions are not checked. To change the alias, edit `schema` in `profiles.yml`.
- The prod profile is committed in `deploy/profiles.yml`, uses service principal OAuth (machine-to-machine), and is used only with `--profiles-dir deploy`.

## Schema naming

- One `generate_schema_name` override:
  - dev: `<product>__<alias>__<layer>` in the team catalog
  - prod: `<layer>` in the product catalog
- Published versions: `<layer>` = `vN`.

## Dev data

- The variable `dev_source_mode` = `prod` | `clone` | `sample`, default `clone`. Sources resolve catalog and schema from it; prod ignores it.
- Clones: personal Delta shallow clones of every declared source table, in `<product>__<alias>__src_clone`. View sources are read from prod.
- Samples: personal small tables in `<product>__<alias>__src_sample`. **How samples are produced is still open**; there will be a separate session on dev data generation.

## Toolkit (Makefile entry points)

| Target | Does |
|---|---|
| `make setup` | Checks Databricks CLI login, suggests and confirms the alias, writes `profiles.yml`, installs dependencies |
| `make clone-sources` | (Re)creates personal shallow clones; also fixes clones broken by prod `VACUUM` |
| `make sample-sources` | (Re)creates personal samples (method TBD) |
| `make build-changed` | Fetches `latest/manifest.json` from the product dev catalog's `_dbt_artifacts.state` volume (the latest release candidate) and runs `dbt build --select state:modified+ --defer --state …` |
| `make clean-dev` | Drops only the current developer's `<product>__<alias>__*` schemas, after confirmation |
| `make contract` | Generates the ODCS data contract(s) locally (deferred: data contracts are out of scope for the first version) |

Data operations are dbt macros run with `dbt run-operation`; setup is a script using the Databricks CLI.

## Data contracts

- dbt files are the source of truth. One ODCS document is generated per active contract version.
- ODCS fields with no place in dbt come from `meta.odcs.*` (product level in `dbt_project.yml`, table and column level in model YAML). Fields that aren't provided are left out.
- Generated contracts are not committed. They will be generated from a `manifest.json` when needed; job runs publish only dbt artifacts.
- **Deferred:** data contracts and breaking-change checks are out of scope for the first version.

## Parked

- Generating dev data and samples (methods, keeping joins intact).
- Checking that all published models carry the same set of versions (risk accepted for now).
- Publishing data contracts to Collibra.
- Python models.

## CI and deployment

Decided in the second grilling session; see `.scratch/ci-cd/spec.md`.

## Pending decision: central platform repository

`.scratch/dev-environment/issues/07-central-platform-repository.md` (status `needs-triage`) proposes moving the setup, dev-environment and deployment tooling into a central, versioned platform repository, so product repos keep only their dbt code. If accepted, it changes parts of this spec. That ticket lists the conflicts and open questions; resolve them with the user before implementing the affected parts.
