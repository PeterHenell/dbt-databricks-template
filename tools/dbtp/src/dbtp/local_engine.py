"""`dbtp local …`: the local engine (Apache Spark + Postgres metastore, `local/compose.yml`).

For trying dbt changes without Databricks. Uses podman-compose if installed (it needs
no podman API socket), else `docker compose`; `$COMPOSE_CMD` overrides that, e.g.
`COMPOSE_CMD="podman compose"`. Runs on the host, not in the dev container, because
it starts containers of its own.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from dbtp import devenv
from dbtp.devenv import Project, SetupError

COMPOSE_FILE = "local/compose.yml"
READY_TIMEOUT_SECONDS = 60


def compose_command(env: Mapping[str, str] = os.environ, which=shutil.which) -> list[str]:
    if configured := env.get("COMPOSE_CMD", "").strip():
        base = shlex.split(configured)
    elif which("podman-compose"):
        base = ["podman-compose"]
    else:
        base = ["docker", "compose"]
    return [*base, "-f", COMPOSE_FILE]


def _compose(project: Project, *args: str) -> int:
    return devenv.run([*compose_command(), *args], project)


def _check(code: int) -> None:
    if code:
        raise SystemExit(code)


def up(project: Project, sleep=time.sleep) -> int:
    """Build the dbt image and start the Postgres metastore; wait until it accepts connections."""
    if os.environ.get("DBT_DEVCONTAINER"):
        raise SetupError("The local engine starts containers of its own: run make local-* "
                         "on the host, not in the dev container.")
    _check(_compose(project, "build", "dbt"))
    _check(_compose(project, "up", "-d", "metastore-db"))
    ready = [*compose_command(), "exec", "-T", "metastore-db",
             "pg_isready", "-q", "-U", "hive", "-d", "metastore"]
    for _ in range(READY_TIMEOUT_SECONDS):
        if subprocess.call(ready, cwd=project.root, stderr=subprocess.DEVNULL) == 0:
            return 0
        sleep(1)
    raise SetupError("metastore-db did not become ready")


def sources(project: Project) -> int:
    """Create the local stand-ins for the sources (`local/sources.sql`)."""
    up(project)
    return _compose(project, "run", "--rm", "spark-sql", "-f", "/project/local/sources.sql")


def relative_package_links(project: Project) -> list[Path]:
    """Make `dbt_packages/` symlinks that point into the repository relative.

    `dbt deps` installs a `local:` package (e.g. the platform macros) as a symlink with
    the absolute host path, which doesn't exist inside the container (the repository is
    mounted at /project). A relative link works on both sides. Returns the links changed.
    """
    changed = []
    packages = project.root / "dbt_packages"
    if not packages.is_dir():
        return changed
    for link in sorted(packages.iterdir()):
        if not link.is_symlink() or not os.path.isabs(os.readlink(link)):
            continue
        target = link.resolve()
        if not target.is_relative_to(project.root):
            continue
        link.unlink()
        link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        changed.append(link)
    return changed


def dbt(project: Project, args: list[str]) -> int:
    """Run dbt in the local engine (default `build`), after `dbt deps` on the host."""
    up(project)
    _check(devenv.run(["dbt", "deps"], project))
    relative_package_links(project)
    return _compose(project, "run", "--rm", "dbt", *(args or ["build"]))


def sql(project: Project) -> int:
    """Open a Spark SQL shell on the local catalog."""
    up(project)
    return _compose(project, "run", "--rm", "spark-sql")


def down(project: Project) -> int:
    """Stop the containers (keeps the data)."""
    return _compose(project, "down")


def clean(project: Project) -> int:
    """Stop and delete all local tables and the catalog."""
    return _compose(project, "down", "-v")
