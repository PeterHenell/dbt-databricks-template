"""MR build (ADR 0009): drop `<product>__mr__*`, then a full `dbt build` into it.

Runs in the MR pipeline as the team identity, in the team catalog of the dev
workspace (`config/dev-environment.toml`), with target `mr` of deploy/profiles.yml.
No `--defer` (deferring to product dev is a planned later improvement), and sources
are read from prod (non-personal targets always do, macros/source_modes.sql).

Authentication: whatever the Databricks SDK finds in the environment. In GitLab that
is OIDC workload identity federation (DATABRICKS_AUTH_TYPE=env-oidc, DATABRICKS_CLIENT_ID,
DATABRICKS_OIDC_TOKEN) or the client-secret fallback (oauth-m2m). The SDK's token is
handed to dbt as DBT_ACCESS_TOKEN, the same way Databricks does in the job.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

import devenv
from devenv import SetupError


def access_token(host: str, config_factory=None) -> str:
    """An OAuth access token for `host` from the SDK's credential chain (no host from env)."""
    if config_factory is None:
        from databricks.sdk.core import Config as config_factory
    try:
        headers = config_factory(host=host).authenticate()
    except Exception as error:  # the SDK raises several types; all mean "not logged in"
        raise SetupError(f"Could not log in to {host}: {error}") from None
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise SetupError(f"The Databricks login for {host} gave no bearer token.")
    return auth.removeprefix("Bearer ")


def dbt_vars(config: devenv.DevConfig) -> str:
    return json.dumps({"deploy_catalog": config.team_catalog, "deploy_warehouse_id": config.warehouse_id})


def commands(config: devenv.DevConfig, extra: list[str]) -> list[list[str]]:
    common = ["--profiles-dir", "deploy", "--target", "mr", "--vars", dbt_vars(config)]
    return [
        ["dbt", "deps"],
        ["dbt", "run-operation", "drop_mr_environment", "--args", "{dry_run: false}", *common],
        ["dbt", "build", *common, *extra],
    ]


def main(argv: list[str] | None = None, config_factory=None, run=subprocess.call) -> int:
    extra = sys.argv[1:] if argv is None else argv
    try:
        config = devenv.read_dev_config()
        env = {
            **os.environ,
            "DBT_HOST": config.hostname,
            "DBT_ACCESS_TOKEN": access_token(config.host, config_factory),
        }
    except SetupError as error:
        devenv.fail(str(error))
    for command in commands(config, extra):
        print("+ " + shlex.join(command), flush=True)
        if (code := run(command, cwd=devenv.REPO_ROOT, env=env)) != 0:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
