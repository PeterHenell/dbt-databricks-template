# 01: Minimal end-to-end skeleton for a personal environment

**What to build:** A developer clones the repo, runs `make setup` and then `dbt build`, and a small sample data product is built into their own personal environment in the team catalog, reading prod sources. Prod builds of the same models land in plain layer schemas in the product catalog. This is the base every other ticket builds on.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] The data product name is set in one project variable and drives both the product catalog and the personal environment prefix
- [x] Python tools (dbt-databricks etc.) are pinned with `uv` and a lockfile; `make setup` installs them
- [x] `make setup` checks for a valid Databricks CLI OAuth login (user-to-machine) and explains how to log in if there isn't one
- [x] `make setup` suggests a developer alias (first 2 letters of first name + first 2 of last name, converted to ASCII: `Peter Henell` → `pehe`, `Åsa Öberg` → `asob`), lets the developer accept or change it, and refuses an empty alias
- [x] `make setup` writes a `profiles.yml` at the repo root: profile name = product name, target `dev`, team catalog, shared dev SQL warehouse, `auth_type: oauth`, `schema: <product>__<alias>`. The file is gitignored
- [x] Running `make setup` again doesn't lose a hand-edited alias without asking
- [x] One `generate_schema_name` override gives `<product>__<alias>__<layer>` in dev and `<layer>` in prod (shown with a parse/compile of the prod target)
- [x] The sample project has one source, a `staging` model, an `intermediate` model and one published model with an enforced dbt contract
- [x] Source locations come from variables, so they can be pointed somewhere else per target
- [x] `dbt build` from the repo root, with no flags, builds and tests everything into the developer's personal environment
- [x] CLAUDE.md is updated with the real setup and build commands and how to run a single model or test

## Comments

**2026-11-04 (implementation):**
- Product name = dbt project `name`; `profile` must repeat it because dbt can't take the profile name from a variable. `scripts/devenv.py` refuses to run if they differ. The product catalog name itself is set by the deployment (`DBT_CATALOG` in `deploy/profiles.yml`, ADR 0008), so it is wired up in ci-cd#01.
- Team settings (host, warehouse, team catalog) are in the committed `config/dev-environment.toml`.
- dbt-databricks' `auth_type: oauth` uses its own browser login (client `dbt-databricks`), not the CLI's token cache. `make setup` checks the CLI login, which the Makefile tooling uses; dbt asks for a browser sign-in once as the same user.
- Alias `mr` is refused (would collide with `<product>__mr__*`, ADR 0009).
- Verified offline: `dbt parse` with a dev profile gives `team_x.sample_product__pehe__{staging,intermediate,v1}`; with `--profiles-dir deploy` gives `<catalog>.{staging,intermediate,v1}`. Unit tests in `tests/`. **Not yet run against a real workspace** (`dbt build`).
