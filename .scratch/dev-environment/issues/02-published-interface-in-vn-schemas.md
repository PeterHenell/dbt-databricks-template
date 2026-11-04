# 02: Published interface in `vN` schemas

**What to build:** Consumers read the published interface from one schema per major contract version (`v1`, `v2`, …), with tables under their plain names. Two versions of the sample published model can be built side by side until the older one's deprecation date.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** ready-for-agent

- [ ] The sample published model uses dbt model versions with a v1 and a v2
- [ ] Version N is built into schema `vN` in prod and `<product>__<alias>__vN` in dev, under the model's plain name (`v1.customers`, not `customers_v1`)
- [ ] Both versions are built while v1's `deprecation_date` is in the future
- [ ] Both versions keep enforced dbt contracts
- [ ] How to add a new major version is documented in short form (all published models move together; see ADR 0003)
