# 02: Job runs publish dbt artifacts

**What to build:** Every successful job run leaves its dbt artifacts in a known place in its own catalog, so developers and later tooling can see what was last built.

**Blocked by:** 01 (Bundle deployable to product dev by hand)

**Status:** done (not yet run on Databricks)

- [x] The bundle creates (or expects) the volume `_dbt_artifacts.state` in the target catalog
- [x] A successful run writes `manifest.json` and `run_results.json` to `latest/` and `runs/<run_id>/`
- [x] A failed run writes nothing, so `latest/` always describes a successful build
- [x] The mechanism is chosen and recorded: dbt `--target-path` pointed at the volume, or a follow-up copy task (see ADR 0006)
- [ ] Shown working on product dev: after a run, `latest/manifest.json` is readable from the dev workspace

## Comments

**2026-11-04 (implementation):**
- Mechanism: **follow-up task** (`publish_dbt_artifacts`, `scripts/publish_dbt_artifacts.py`), recorded in `docs/ci-cd.md` and ADR 0006. Rejected `--target-path` on the volume: dbt writes `run_results.json` even for a failed build.
- The task runs only if `dbt_build` succeeded (default `run_if`), reads the dbt task's archived output (`jobs.get_run_output(task_run_id).dbt_output.artifacts_link`), takes `target/manifest.json` and `target/run_results.json` and writes `runs/<job_run_id>/` first, then `latest/`.
- The bundle creates the `_dbt_artifacts` schema and `state` volume (`resources/dbt_job.yml`).
- Unit-tested with a fake SDK client (`tests/test_publish_dbt_artifacts.py`).
- **Not verified:** `{{job.run_id}}` substitution in `spark_python_task` parameters, the archive's layout (the script searches for the nearest `target/`), and the last criterion.
