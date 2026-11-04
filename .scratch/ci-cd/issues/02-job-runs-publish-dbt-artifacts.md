# 02: Job runs publish dbt artifacts

**What to build:** Every successful job run leaves its dbt artifacts in a known place in its own catalog, so developers and later tooling can see what was last built.

**Blocked by:** 01 (Bundle deployable to product dev by hand)

**Status:** ready-for-agent

- [ ] The bundle creates (or expects) the volume `_dbt_artifacts.state` in the target catalog
- [ ] A successful run writes `manifest.json` and `run_results.json` to `latest/` and `runs/<run_id>/`
- [ ] A failed run writes nothing, so `latest/` always describes a successful build
- [ ] The mechanism is chosen and recorded: dbt `--target-path` pointed at the volume, or a follow-up copy task (see ADR 0006)
- [ ] Shown working on product dev: after a run, `latest/manifest.json` is readable from the dev workspace
