"""Offline tests of the dbt macros, run through `dbt run-operation` with a throwaway profile.

The macros under test run no SQL when their inputs are passed in, so no Databricks
connection (and no login) is needed.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dbtp import devenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = devenv.DevConfig("https://adb-1.2.azuredatabricks.net", "wh1", "team_x")
# The data product name, whatever `dbtp init` set it to.
PRODUCT = devenv.read_product(REPO_ROOT / "dbt_project.yml")

SCHEMAS = [
    f"{PRODUCT}__pe",
    f"{PRODUCT}__pe__staging",
    f"{PRODUCT}__pe__src_clone",
    f"{PRODUCT}__pehe__staging",   # an alias that starts with `pe`
    f"{PRODUCT}__pe_he__staging",  # an alias with an underscore
    f"{PRODUCT}__mr__staging",     # the shared MR schemas
    "other_product__pe__staging",      # another data product
    f"{PRODUCT}_pe__staging",      # single underscore
    "default",
]


def run_operation(tmp_path: Path, alias: str, macro: str, args: dict) -> subprocess.CompletedProcess:
    (tmp_path / "profiles.yml").write_text(devenv.render_profile(PRODUCT, alias, CONFIG))
    return subprocess.run(
        ["dbt", "-q", "run-operation", macro, "--args", json.dumps(args),
         "--profiles-dir", str(tmp_path), "--target-path", str(tmp_path / "target"),
         "--log-path", str(tmp_path / "logs")],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=180,
    )


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("pe", [f"{PRODUCT}__pe", f"{PRODUCT}__pe__src_clone", f"{PRODUCT}__pe__staging"]),
        ("pehe", [f"{PRODUCT}__pehe__staging"]),
        ("pe_he", [f"{PRODUCT}__pe_he__staging"]),
    ],
)
def test_clean_dev_only_matches_own_schemas(tmp_path, alias, expected):
    result = run_operation(tmp_path, alias, "drop_personal_environment",
                           {"dry_run": True, "schemas": SCHEMAS})
    assert result.returncode == 0, result.stdout + result.stderr
    listed = [line.strip() for line in result.stdout.splitlines() if line.startswith("  ")]
    assert listed == expected


def test_clean_dev_refuses_mr_alias(tmp_path):
    result = run_operation(tmp_path, "mr", "drop_personal_environment",
                           {"dry_run": True, "schemas": SCHEMAS})
    assert result.returncode != 0
    assert "reserved" in result.stdout + result.stderr


def test_clean_dev_with_nothing_to_drop(tmp_path):
    result = run_operation(tmp_path, "zz", "drop_personal_environment",
                           {"dry_run": True, "schemas": SCHEMAS})
    assert result.returncode == 0
    assert result.stdout.startswith("Nothing to drop")


def run_mr_operation(tmp_path: Path, target: str, args: dict) -> subprocess.CompletedProcess:
    """drop_mr_environment through the deployment profile (deploy/profiles.yml)."""
    env = {**os.environ, "DBT_HOST": "adb-1.2.azuredatabricks.net", "DBT_ACCESS_TOKEN": "unused"}
    return subprocess.run(
        ["dbt", "-q", "run-operation", "drop_mr_environment", "--args", json.dumps(args),
         "--profiles-dir", "deploy", "--target", target,
         "--vars", "{deploy_catalog: team_x, deploy_warehouse_id: wh1}",
         "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False, timeout=180,
    )


def test_mr_build_drops_only_the_mr_schemas(tmp_path):
    schemas = SCHEMAS + [f"{PRODUCT}__mr", f"{PRODUCT}__mr__v1", f"{PRODUCT}__mrx__staging"]
    result = run_mr_operation(tmp_path, "mr", {"dry_run": True, "schemas": schemas})
    assert result.returncode == 0, result.stdout + result.stderr
    listed = [line.strip() for line in result.stdout.splitlines() if line.startswith("  ")]
    assert listed == [f"{PRODUCT}__mr", f"{PRODUCT}__mr__staging", f"{PRODUCT}__mr__v1"]


def test_mr_drop_refuses_prod_target(tmp_path):
    result = run_mr_operation(tmp_path, "prod", {"dry_run": True, "schemas": SCHEMAS})
    assert result.returncode != 0
    assert "only runs in target 'mr'" in result.stdout + result.stderr


# ---- The platform package's stubs (macros/dbt_platform.sql) ----


def test_stubs_apply_the_package_schema_and_alias_names(tmp_path):
    """Parsing applies generate_schema_name/generate_alias_name: personal layer schemas,
    published versions in `vN` under the plain model name."""
    (tmp_path / "profiles.yml").write_text(devenv.render_profile(PRODUCT, "pe", CONFIG))
    result = subprocess.run(
        ["dbt", "-q", "parse", "--profiles-dir", str(tmp_path), "--target-path", str(tmp_path / "target"),
         "--log-path", str(tmp_path / "logs")],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    nodes = json.loads((tmp_path / "target" / "manifest.json").read_text())["nodes"]
    models = [n for n in nodes.values()
              if n["resource_type"] == "model" and n["package_name"] == PRODUCT]
    # Whatever the product's models are: a staging model, and a version of a published one.
    staging = next(n for n in models if n["config"]["schema"] == "staging")
    assert staging["schema"] == f"{PRODUCT}__pe__staging" and staging["alias"] == staging["name"]
    published = next(n for n in models if n["config"]["schema"] == "published")
    assert published["version"] is not None
    assert published["schema"] == f"{PRODUCT}__pe__v{published['version']}"
    assert published["alias"] == published["name"]  # plain name, no `_vN`


# Run dbt in-process with the Databricks adapter's `execute` replaced, so macros that
# run SQL print it instead of connecting.
PRINT_SQL_RUNNER = """
import sys, agate
from dbt.adapters.contracts.connection import AdapterResponse
from dbt.adapters.databricks.impl import DatabricksAdapter
def execute(self, sql, auto_begin=False, fetch=False, limit=None):
    print("SQL>", " ".join(sql.split()))
    return AdapterResponse("OK"), agate.Table([])
DatabricksAdapter.execute = execute
from dbt.cli.main import dbtRunner
sys.exit(0 if dbtRunner().invoke(sys.argv[1:]).success else 1)
"""

NOT_NULL_PROBE = """
{% macro probe_not_null() %}
    {% set relation = api.Relation.create(database='c', schema='s', identifier='t') %}
    {% set model = {'columns': {'id': {'name': 'id', 'quote': false, 'constraints': [{'type': 'not_null'}]}}} %}
    {% do alter_column_set_constraints(relation, model) %}
{% endmacro %}
"""


def test_databricks_contracts_keep_the_adapters_not_null(tmp_path):
    """The local-Spark NOT NULL override must not replace dbt-databricks' own macro.

    For namespace `dbt` dbt searches the root project first, with every adapter prefix,
    so the root's `spark__alter_column_set_constraints` stub is what Databricks reaches;
    the package must hand the call back (SET NOT NULL, not a CHECK constraint).
    """
    project = tmp_path / "project"
    project.mkdir()
    for name in ("dbt_project.yml", "packages.yml"):
        shutil.copy(REPO_ROOT / name, project / name)
    for name in ("macros", "models", "seeds", "snapshots"):
        if (REPO_ROOT / name).is_dir():
            shutil.copytree(REPO_ROOT / name, project / name)
    shutil.copytree(REPO_ROOT / "tools" / "dbt_platform", project / "dbt_packages" / "dbt_platform",
                    ignore=shutil.ignore_patterns("target", "logs"))
    (project / "macros" / "probe_not_null.sql").write_text(NOT_NULL_PROBE)
    (tmp_path / "profiles.yml").write_text(devenv.render_profile(PRODUCT, "pe", CONFIG))

    result = subprocess.run(
        [sys.executable, "-c", PRINT_SQL_RUNNER, "-q", "run-operation", "probe_not_null",
         "--profiles-dir", str(tmp_path), "--log-path", str(tmp_path / "logs")],
        cwd=project, env={**os.environ, "DO_NOT_TRACK": "1"},
        capture_output=True, text=True, check=False, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    statements = [line for line in result.stdout.splitlines() if line.startswith("SQL>")]
    assert statements == ["SQL> alter table `c`.`s`.`t` change column `id` set not null ;"]
