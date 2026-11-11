"""What this repository's release artifact holds (dbtp.release on the template itself)."""

from pathlib import Path

from dbtp import devenv, release

ROOT = Path(__file__).resolve().parent.parent


def test_project_name_matches_profile():
    devenv.read_product(ROOT / "dbt_project.yml")  # raises unless `name` == `profile` and valid


def test_artifact_holds_the_deployable_project_only():
    files = release.tracked_files(ROOT)
    assert "databricks.yml" in files and "deploy/profiles.yml" in files
    assert release.JOB_SCRIPT in files and "dbt_project.yml" in files
    assert any(f.startswith("models/") for f in files) and any(f.startswith("macros/") for f in files)
    for left_out in ("Makefile", ".gitlab-ci.yml", "config/dev-environment.toml",
                     "tools/dbtp/src/dbtp/devenv.py", "tools/dbtp/src/dbtp/jobs/__init__.py"):
        assert left_out not in files
    assert not any(f.startswith(("local/", "docs/", "tests/test_")) for f in files)
    assert "profiles.yml" not in files  # the developer's own profile, never shipped (ADR 0002)


def test_bundle_job_runs_the_shipped_script():
    job = (ROOT / "resources" / "dbt_job.yml").read_text()
    assert f"python_file: ../{release.JOB_SCRIPT}" in job


def test_artifact_ships_the_platform_package_as_files():
    # dbt deps (tests/conftest.py) installs the local package as a symlink; the job never
    # runs dbt deps, so the artifact must carry the package's files.
    files = release.installed_files(ROOT)
    assert "dbt_packages/dbt_platform/dbt_project.yml" in files
    assert "dbt_packages/dbt_platform/macros/source_modes.sql" in files
    assert "macros/dbt_platform.sql" in release.tracked_files(ROOT)
