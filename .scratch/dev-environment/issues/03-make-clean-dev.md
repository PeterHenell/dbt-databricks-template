# 03: `make clean-dev`

**What to build:** A developer can remove their whole personal environment for this data product with one command, without any risk to teammates' environments or the shared MR schemas.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** done

- [x] `make clean-dev` lists the schemas it will drop and asks for confirmation
- [x] Only schemas with the prefix `<product>__<alias>__` (from the developer's `profiles.yml`) are dropped, including source clone/sample schemas
- [x] Other developers' schemas, other products' schemas and `<product>__mr__*` are never matched, even when one alias is a prefix of another (e.g. `pe` vs `pehe`)
- [x] Runs as a dbt `run-operation` using the developer's own profile

## Comments

**2026-11-04 (implementation):**
- `macros/personal_environment.sql`: `drop_personal_environment(dry_run=true)`; `make clean-dev` prints the dry run, asks for `yes`, then drops with `drop schema … cascade`.
- Matching is an exact `startswith('<product>__<alias>__')` (plus the bare `<product>__<alias>`, which can only be this developer's). It refuses target `prod`, a `schema` that isn't `<product>__<alias>`, and alias `mr`.
- The second call lists schemas again rather than reusing the confirmed list; a schema created in between with the same prefix would also be dropped (it's still this developer's).
- Verified on the local Spark engine (local/): with `pe`, `pehe`, `pe_he`, `mr`, `other_product__pe` and `sample_product_pe` schemas present, only the three `sample_product__pe*` schemas were dropped. Offline regression tests in `tests/test_macros.py`. Not yet run on Databricks.
