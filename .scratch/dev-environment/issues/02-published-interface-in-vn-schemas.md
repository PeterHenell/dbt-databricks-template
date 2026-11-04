# 02: Published interface in `vN` schemas

**What to build:** Consumers read the published interface from one schema per major contract version (`v1`, `v2`, …), with tables under their plain names. Two versions of the sample published model can be built side by side until the older one's deprecation date.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** done

- [x] The sample published model uses dbt model versions with a v1 and a v2
- [x] Version N is built into schema `vN` in prod and `<product>__<alias>__vN` in dev, under the model's plain name (`v1.customers`, not `customers_v1`)
- [x] Both versions are built while v1's `deprecation_date` is in the future
- [x] Both versions keep enforced dbt contracts
- [x] How to add a new major version is documented in short form (all published models move together; see ADR 0003)

## Comments

**2026-11-04 (implementation):**
- `customers` has v1 (`deprecation_date: 2027-06-30`) and v2 (renames `lifetime_value` → `total_order_value`, drops `market_segment`), files `customers_v1.sql` / `customers_v2.sql`; `latest_version: 2`.
- The `published` folder has `+schema: published`; `generate_schema_name` turns that into `vN` from the node's version, and `generate_alias_name` keeps the plain name.
- dbt calls `generate_schema_name` once before the YAML `versions:` are applied, so "published models must be versioned" can't be enforced there. It is an `on-run-start` check (`assert_published_models_are_versioned`) instead; verified it rejects an unversioned model.
- Expired versions are not disabled automatically: dbt warns after the `deprecation_date`, and retiring the version is a manual delete (documented in `docs/published-interface.md`).
- Verified with `dbt parse`: dev `team_x.sample_product__pehe__v1.customers` / `__v2.customers`, prod `<catalog>.v1.customers` / `v2.customers`, both contracts enforced.
