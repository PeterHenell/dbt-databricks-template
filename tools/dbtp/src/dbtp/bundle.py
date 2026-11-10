"""`dbtp bundle validate|deploy|run`: the Databricks Asset Bundle (databricks.yml, resources/).

Deploys always go from the unpacked release artifact (`dbtp release build`, or
`release fetch` in CI), so a hand deploy ships exactly what a release would (ADR 0008).
"""

from __future__ import annotations

from pathlib import Path

from dbtp import devenv, release
from dbtp.devenv import Project, SetupError

JOB = "dbt_build"  # the job's resource key in resources/dbt_job.yml


def _artifact_dir(project: Project) -> Path:
    path = release.bundle_dir(project)
    if not (path / "databricks.yml").is_file():
        raise SetupError(
            f"No unpacked artifact in {path.relative_to(project.root)}: run `make artifact` "
            "(dbtp release build) first."
        )
    return path


def _bundle(directory: Path, *args: str) -> int:
    return devenv.run(["databricks", "bundle", *args], Project(directory))


def validate(project: Project, target: str, directory: Path | None = None) -> int:
    """Validate the bundle for `target`, in the repository or in `directory` (e.g. the artifact)."""
    path = project.root / directory if directory else project.root
    return _bundle(path, "validate", "-t", target)


def deploy(project: Project, target: str) -> int:
    return _bundle(_artifact_dir(project), "deploy", "-t", target)


def run(project: Project, target: str) -> int:
    """Start the job in `target` and wait for it; fails if the run fails."""
    return _bundle(_artifact_dir(project), "run", "-t", target, JOB)
