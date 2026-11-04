# 04: Source modes and `make clone-sources`

**What to build:** By default a developer works against personal shallow clones of the prod sources instead of reading prod directly. One variable switches all sources between prod and clones, and one command creates or refreshes the clones.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** done

- [x] Variable `dev_source_mode` accepts `prod` and `clone` (default `clone`); `sample` is reserved but not implemented yet (method still undecided)
- [x] In `clone` mode every source resolves to `<product>__<alias>__src_clone` in the team catalog
- [x] `make clone-sources` creates or replaces a Delta shallow clone of every declared source table in that schema
- [x] Sources that are views are not cloned and resolve to prod in every mode; the command says which ones it skipped
- [x] Re-running `make clone-sources` fixes clones broken by prod `VACUUM`
- [x] Prod and CI targets ignore `dev_source_mode` and always read prod sources
- [x] The mode can be overridden per run (`--vars`)

## Comments

**2026-11-04 (implementation):**
- `macros/source_modes.sql` overrides dbt's `source()` (via `builtins.source`, so lineage is unchanged): personal targets (`dev`, `local`) in `clone` mode read `<product>__<alias>__src_clone.<source>__<table>`; every other target reads the prod location from the source YAML. The source YAML can't set a schema per table, so the override is what makes per-table choices possible.
- **Deviation:** views are not cloned, but instead of resolving them to the prod name, `make clone-sources` creates a view of the same name in the clone schema that selects from the prod view. Data still always comes from prod, and resolution stays one rule. The command lists the skipped views.
- Re-creating a clone: `create or replace … shallow clone` on Databricks; on open-source Delta (local engine) that fails for a non-empty table, so the local engine drops and re-creates (`shallow_clone_table` dispatch).
- Verified on the local engine: clone, re-clone, a view source, build in clone mode (20/20), `--vars '{dev_source_mode: prod}'`, `sample` error, target `prod` ignoring the mode. A clone broken by prod `VACUUM` could not be reproduced locally (open-source Delta wrote deletion vectors, so VACUUM removed nothing); re-running did refresh the clone to prod's current state.
- Not verified: whether Databricks allows shallow clones of `samples.tpch` (the sample source); a real product's sources will be ordinary Unity Catalog tables.
