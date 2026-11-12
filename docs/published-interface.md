# The published interface

Consumers read the published data product from one schema, `published`, in the product catalog (`<product>__<alias>__published` in your personal environment). Tables have their plain model names: `published.customers`. Everything outside `models/published/` is internal and may change at any time.

## How it is built

- Models in `models/published/` are tables in layer `published` (`+schema: published` in `dbt_project.yml`).
- Every published model has an enforced contract: a `data_type` on every column in `models/published/_published.yml`. dbt refuses to build the model if its result doesn't have exactly those columns and types, so a change to a column always shows up in the YAML.
- Give the key `unique` and `not_null` tests, like every model.

## Changing a published model

There is no versioning mechanism in the template (ADR 0010). What protects consumers is how the team works:

- **Non-breaking changes** (a new column, a fix that keeps the columns, types and grain) go through the normal feature flow.
- **Breaking changes** (removing or renaming a column, changing a type or the grain) need a decision, not just a merge request. Before you make one, find out who reads the model, agree a date with them, and say in the MR that it is breaking. Reviewers check every MR that touches `models/published/` for breaking changes.

If a product really needs an old and a new version side by side for a while, use dbt's [model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions) as dbt ships them, without platform changes: version N is built as `published.<model>_vN`, and the `latest_version_pointer` config can keep a plain-name view on the latest one. ADR 0010 has the details. Which mechanism becomes the team standard is still open.
