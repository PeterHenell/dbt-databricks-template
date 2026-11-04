# 03: `make clean-dev`

**What to build:** A developer can remove their whole personal environment for this data product with one command, without any risk to teammates' environments or the shared MR schemas.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** ready-for-agent

- [ ] `make clean-dev` lists the schemas it will drop and asks for confirmation
- [ ] Only schemas with the prefix `<product>__<alias>__` (from the developer's `profiles.yml`) are dropped, including source clone/sample schemas
- [ ] Other developers' schemas, other products' schemas and `<product>__mr__*` are never matched, even when one alias is a prefix of another (e.g. `pe` vs `pehe`)
- [ ] Runs as a dbt `run-operation` using the developer's own profile
