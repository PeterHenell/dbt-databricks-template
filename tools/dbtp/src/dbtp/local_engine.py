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
    """Create the small stand-in `tpch` source tables."""
    up(project)
    return _compose(project, "run", "--rm", "spark-sql", "-f", "/project/local/tpch.sql")


def dbt(project: Project, args: list[str]) -> int:
    """Run dbt in the local engine (default `build`)."""
    up(project)
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
