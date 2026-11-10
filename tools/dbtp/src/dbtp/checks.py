"""Offline checks of the dbt project that need no Databricks login."""

from __future__ import annotations

import os

from dbtp import devenv
from dbtp.devenv import Project

# The deploy profile reads these; any value works because parse never connects.
PARSE_ENV = {"DBT_HOST": "parse.invalid", "DBT_ACCESS_TOKEN": "unused"}
PARSE_VARS = "{deploy_catalog: parse, deploy_warehouse_id: parse}"


def parse_command() -> list[str]:
    return ["dbt", "parse", "--profiles-dir", "deploy", "--target", "mr", "--vars", PARSE_VARS]


def parse(project: Project) -> int:
    """`dbt deps`, then `dbt parse` with the deployment profile (ADR 0002), no connection
    and no login. Parsing needs the installed packages, e.g. the platform macros."""
    env = {**os.environ, **PARSE_ENV}
    return devenv.run(["dbt", "deps"], project, env=env) or devenv.run(parse_command(), project, env=env)
