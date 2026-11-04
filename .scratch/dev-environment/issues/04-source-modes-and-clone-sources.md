# 04: Source modes and `make clone-sources`

**What to build:** By default a developer works against personal shallow clones of the prod sources instead of reading prod directly. One variable switches all sources between prod and clones, and one command creates or refreshes the clones.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** ready-for-agent

- [ ] Variable `dev_source_mode` accepts `prod` and `clone` (default `clone`); `sample` is reserved but not implemented yet (method still undecided)
- [ ] In `clone` mode every source resolves to `<product>__<alias>__src_clone` in the team catalog
- [ ] `make clone-sources` creates or replaces a Delta shallow clone of every declared source table in that schema
- [ ] Sources that are views are not cloned and resolve to prod in every mode; the command says which ones it skipped
- [ ] Re-running `make clone-sources` fixes clones broken by prod `VACUUM`
- [ ] Prod and CI targets ignore `dev_source_mode` and always read prod sources
- [ ] The mode can be overridden per run (`--vars`)
