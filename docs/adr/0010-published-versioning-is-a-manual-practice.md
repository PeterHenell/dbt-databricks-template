# Versioning the published interface is a team practice, not tooling

Supersedes [ADR 0003](0003-published-interface-versioned-per-product.md).

The published models are built into one schema, `published`, under their plain names (`published.customers`), and that schema is the published data product. The template no longer has a built-in versioning mechanism: no `vN` schemas, no `generate_alias_name` override that strips `_vN`, no run-start check that rejects an unversioned published model, and the sample product has one unversioned `customers` model. Breaking changes are kept under control by training and governance (review of changes to `models/published/`, talking to consumers before a change), not by the build. Which mechanism to use when a product does need two versions side by side, for example a `published_v2` schema or dbt model versions, will be decided later, in its own ADR.

We made this change because ADR 0003's machinery cost more than it gave a team with moderate data-engineering experience: every published model had to be split into `<model>_vN.sql` files with `versions:` YAML from day one, platform macros renamed models and schemas, and a breaking change meant copying every published model. Most products will rarely make breaking changes, and when they do, a deliberate decision by the team is the real safeguard.

## Consequences

- Nothing in the build stops a breaking change to a published model. Reviewers of a merge request that touches `models/published/` are responsible for spotting one and for making sure consumers are told (`docs/published-interface.md`).
- Enforced dbt contracts stay on for published models (ADR 0004), so a change to a column's name or type is always visible in the YAML diff and caught at build time if the SQL and YAML disagree.
- Until a versioning mechanism is chosen, ADR 0004's "one ODCS document per active contract version" means one data contract for the `published` schema.
- A team that needs two versions side by side before that decision should use dbt's standard way, described below. Nothing in the platform package depends on it.

## The dbt standard, for when versions are needed

dbt's own answer is [model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions), used together with enforced contracts. It is the option to try first when the later decision is made:

- Versions are declared per model, not per product: `versions:` and `latest_version:` in the model's YAML, one SQL file per version, with each version picking its columns with `include`/`exclude`.
- dbt recommends simple major versioning: a new version only for a breaking change, and non-breaking changes whenever possible.
- By dbt's standard naming, version N is built as `<model>_v<N>` in the model's usual schema (`published.customers_v2`), so old and new versions sit side by side.
- The `latest_version_pointer` config makes dbt create a view with the plain name (`published.customers`) that always points to the latest version, for consumers that want a stable name.
- `ref('customers')` resolves to the latest version; a model inside dbt pins one with `ref('customers', v=1)`.
- The old version gets a `deprecation_date`. dbt warns about references to a version past that date and does not drop its table, so the team deletes the version and drops the table by hand.

ADR 0003 bent this into one `vN` schema per product with plain table names, which is what needed the custom macros. Using model versions as dbt ships them needs no platform code.
