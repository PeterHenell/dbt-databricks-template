"""`dbtp bundle validate|deploy|run`: the Databricks Asset Bundle (databricks.yml, resources/).

Deploys always go from the unpacked release artifact (`dbtp release build`, or
`release fetch` in CI), so a hand deploy ships exactly what a release would (ADR 0008).

Each command first refuses a target that still has a template `<placeholder>`, with a
list of them, instead of letting the Databricks CLI fail on it with a credentials error.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from dbtp import devenv, release
from dbtp.devenv import Project, SetupError

JOB = "dbt_build"  # the job's resource key in resources/dbt_job.yml


def _artifact_dir(project: Project) -> Path:
    path = release.bundle_dir(project)
    if not (path / "databricks.yml").is_file():
        raise SetupError(
            f"No unpacked artifact in {path.relative_to(project.root)}: run "
            "`uv run dbtp release build` first."
        )
    return path


PLACEHOLDER = re.compile(r"<[^<>\s]+>")


def find_placeholders(data, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    """Every (key path, value) in parsed YAML whose value still holds a `<placeholder>`."""
    if isinstance(data, dict):
        return [found for key, value in data.items()
                for found in find_placeholders(value, (*path, str(key)))]
    if isinstance(data, list):
        return [found for index, value in enumerate(data)
                for found in find_placeholders(value, (*path, str(index)))]
    if isinstance(data, str) and PLACEHOLDER.search(data):
        return [(path, data)]
    return []


def target_placeholders(config: dict, target: str) -> list[tuple[tuple[str, ...], str]]:
    """Placeholders that a deploy of `target` would use: the target and everything outside
    `targets` (other targets don't matter)."""
    shared = {key: value for key, value in config.items() if key != "targets"}
    chosen = {"targets": {target: (config.get("targets") or {}).get(target)}}
    return find_placeholders(shared) + find_placeholders(chosen)


def check_filled(directory: Path, target: str) -> None:
    """Raise SetupError, naming each one, if `target` in `directory`'s databricks.yml has
    placeholders left."""
    path = directory / "databricks.yml"
    if not path.is_file():
        return  # the Databricks CLI reports a missing bundle itself
    left = target_placeholders(yaml.safe_load(path.read_text()) or {}, target)
    if left:
        lines = "\n".join(f"  {'.'.join(key)}: {value}" for key, value in left)
        raise SetupError(
            f"databricks.yml: target '{target}' still has template placeholders:\n{lines}\n"
            "Run `uv run dbtp init` to fill them in (`uv run dbtp init --help` lists the "
            "options), then commit databricks.yml.")


def _bundle(directory: Path, *args: str) -> int:
    return devenv.run(["databricks", "bundle", *args], Project(directory))


def validate(project: Project, target: str, directory: Path | None = None) -> int:
    """Validate the bundle for `target`, in the repository or in `directory` (e.g. the artifact)."""
    path = project.root / directory if directory else project.root
    check_filled(path, target)
    return _bundle(path, "validate", "-t", target)


def deploy(project: Project, target: str) -> int:
    path = _artifact_dir(project)
    check_filled(path, target)
    return _bundle(path, "deploy", "-t", target)


def run(project: Project, target: str) -> int:
    """Start the job in `target` and wait for it; fails if the run fails."""
    path = _artifact_dir(project)
    check_filled(path, target)
    return _bundle(path, "run", "-t", target, JOB)
