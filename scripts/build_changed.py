"""`make build-changed`: a deferred build of only the models you changed.

1. Downloads `latest/manifest.json` from the product dev catalog's `_dbt_artifacts.state`
   volume (the latest release candidate, ADR 0006), with your own Databricks CLI login.
2. Runs `dbt build --select state:modified+ --defer --state <download>` into your
   personal environment. References to unchanged models resolve to the product dev
   catalog through the downloaded manifest.

Extra arguments are passed on to dbt, e.g. `make build-changed ARGS="--exclude published"`.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

import devenv
from devenv import SetupError
from setup_dev import cli_access_token

STATE_DIR = devenv.REPO_ROOT / "target" / "product-dev-state"


def download_manifest(host: str, catalog: str, state_dir: Path = STATE_DIR) -> Path:
    source = f"dbfs:{devenv.artifacts_volume_path(catalog)}/latest/manifest.json"
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / "manifest.json"
    target.unlink(missing_ok=True)
    # `fs cp` has no --host flag. Use the developer's U2M login (`databricks auth login
    # --host …`) for exactly this host, ignoring any ~/.databrickscfg profiles.
    env = {
        **os.environ,
        "DATABRICKS_HOST": host,
        "DATABRICKS_AUTH_TYPE": "databricks-cli",
        "DATABRICKS_CONFIG_FILE": os.devnull,
    }
    env.pop("DATABRICKS_CONFIG_PROFILE", None)
    result = subprocess.run(
        ["databricks", "fs", "cp", "--overwrite", source, str(target)],
        capture_output=True, text=True, check=False, env=env,
    )
    if result.returncode != 0 or not target.exists():
        output = (result.stderr + result.stdout).strip()
        if any(hint in output.lower() for hint in ("not exist", "not found", "no such")):
            raise SetupError(
                f"No product dev manifest at {source}.\n"
                "  No product dev job run has published dbt artifacts yet (a release has to be\n"
                "  deployed to product dev and its job run successfully). Until then use a full\n"
                "  build: `uv run dbt build`."
            )
        raise SetupError(f"Could not download {source}:\n  {output}")
    return target


def dbt_command(state_dir: Path, extra: list[str]) -> list[str]:
    return [
        "dbt", "build",
        "--select", "state:modified+",
        "--defer", "--state", str(state_dir),
        *extra,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest-dir", type=Path,
                        help="use a manifest.json already in this directory instead of downloading it")
    parser.add_argument("dbt_args", nargs="*", help="extra arguments for dbt build")
    args = parser.parse_args()

    try:
        if args.manifest_dir:
            state_dir = args.manifest_dir
            if not (state_dir / "manifest.json").exists():
                raise SetupError(f"No manifest.json in {state_dir}")
        else:
            config = devenv.read_dev_config()
            catalog = devenv.read_product_dev_catalog()
            cli_access_token(config.host)  # clear message if not logged in
            download_manifest(config.host, catalog)
            print(f"Deferring to the product dev manifest of catalog {catalog}.")
            state_dir = STATE_DIR
    except SetupError as error:
        devenv.fail(str(error))

    command = dbt_command(state_dir, args.dbt_args)
    print("+ " + shlex.join(command), flush=True)
    sys.exit(subprocess.call(command, cwd=devenv.REPO_ROOT))


if __name__ == "__main__":
    main()
