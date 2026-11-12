# The published interface is versioned per product, one schema per major version

> **Superseded** by [ADR 0010](0010-published-versioning-is-a-manual-practice.md) (2026-11-12): the `vN` schemas and the tooling that enforced them are removed.

The published interface is versioned as a whole: a breaking change to any published model creates a new contract version, and every published model is built into schema `vN` under its plain name (`v1.customers`, not `customers_v1`). We considered versioning each model separately, which matches dbt model versions one-to-one. We rejected it because then a `vN` schema could hold only part of the product, and an ODCS data contract describes a whole product. dbt model versions are still how `v1` and `v2` are built side by side until the older version's `deprecation_date`.

## Consequences

- Nothing checks that every published model has the same set of active versions. We accept that risk for now, since such a check was judged too complicated.
