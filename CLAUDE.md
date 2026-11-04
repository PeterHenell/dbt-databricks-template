# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repository is a **git repository template** for dbt projects running on Databricks. Teams create new repos from it, so everything here should be generic, clearly documented, and easy to rename/adapt (avoid hard-coding a specific workspace, catalog, or team name — use placeholders or variables).

The template has two primary functional goals; design decisions should be evaluated against them:

1. **Isolated development environments** — every member of a data engineering team can develop and run dbt against Databricks without affecting teammates or shared environments. A developer's `dbt run`/`dbt build` must only ever write to objects owned by that developer's environment, and the isolation must hold without per-developer manual setup beyond credentials.
2. **Deployment pattern** — a repeatable, automated way to deploy the dbt project to Databricks for shared environments (e.g. test/prod), driven from CI/CD rather than from developer machines.

Beyond those, the template should embody dbt best practices (project layering, naming conventions, testing, documentation) and Databricks-specific best practices for the dbt-databricks adapter.

## Current state

The repository is newly initialized and has no commits or code yet. As the template is built out, update this file with:

- The actual commands for setup, `dbt build`, linting, and running a single model/test.
- How developer isolation is implemented (the mechanism, and which files implement it).
- How deployment works end-to-end (which tool, which targets, what CI triggers it).

Do not document conventions here until they exist in the repo.

## Agent skills

### Issue tracker

Issues and specs are tracked as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
