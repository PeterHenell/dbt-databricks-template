# 01: Minimal end-to-end skeleton for a personal environment

**What to build:** A developer clones the repo, runs `make setup` and then `dbt build`, and a small sample data product is built into their own personal environment in the team catalog, reading prod sources. Prod builds of the same models land in plain layer schemas in the product catalog. This is the base every other ticket builds on.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The data product name is set in one project variable and drives both the product catalog and the personal environment prefix
- [ ] Python tools (dbt-databricks etc.) are pinned with `uv` and a lockfile; `make setup` installs them
- [ ] `make setup` checks for a valid Databricks CLI OAuth login (user-to-machine) and explains how to log in if there isn't one
- [ ] `make setup` suggests a developer alias (first 2 letters of first name + first 2 of last name, converted to ASCII: `Peter Henell` → `pehe`, `Åsa Öberg` → `asob`), lets the developer accept or change it, and refuses an empty alias
- [ ] `make setup` writes a `profiles.yml` at the repo root: profile name = product name, target `dev`, team catalog, shared dev SQL warehouse, `auth_type: oauth`, `schema: <product>__<alias>`. The file is gitignored
- [ ] Running `make setup` again doesn't lose a hand-edited alias without asking
- [ ] One `generate_schema_name` override gives `<product>__<alias>__<layer>` in dev and `<layer>` in prod (shown with a parse/compile of the prod target)
- [ ] The sample project has one source, a `staging` model, an `intermediate` model and one published model with an enforced dbt contract
- [ ] Source locations come from variables, so they can be pointed somewhere else per target
- [ ] `dbt build` from the repo root, with no flags, builds and tests everything into the developer's personal environment
- [ ] CLAUDE.md is updated with the real setup and build commands and how to run a single model or test
