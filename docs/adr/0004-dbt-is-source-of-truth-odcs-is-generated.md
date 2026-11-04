# dbt is the source of truth; ODCS data contracts are generated

Data contracts follow the Open Data Contract Standard (ODCS), but the dbt project files are the source of truth, because that is where the work is done. One ODCS document per active contract version is generated from the dbt manifest. ODCS fields dbt has no place for (owner, support, SLAs, terms) go in `meta.odcs.*` blocks in dbt YAML. Fields that aren't provided are left out, not made up. Generated contracts are not committed. Their main job is detecting breaking changes made without a new contract version, and later they will be published to Collibra. We rejected hand-editing the ODCS files and generating dbt from them, because it moves the work out of dbt.

## Consequences

- dbt's enforced model contracts (`contract: {enforced: true}`) stay on for published models, to catch type drift at build time.
