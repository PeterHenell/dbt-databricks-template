"""Offline tests of the dbt macros, run through `dbt run-operation` with a throwaway profile.

The macros under test run no SQL when their inputs are passed in, so no Databricks
connection (and no login) is needed.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from dbtp import devenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = devenv.DevConfig("https://adb-1.2.azuredatabricks.net", "wh1", "team_x")

SCHEMAS = [
    "sample_product__pe",
    "sample_product__pe__staging",
    "sample_product__pe__src_clone",
    "sample_product__pehe__staging",   # an alias that starts with `pe`
    "sample_product__pe_he__staging",  # an alias with an underscore
    "sample_product__mr__staging",     # the shared MR schemas
    "other_product__pe__staging",      # another data product
    "sample_product_pe__staging",      # single underscore
    "default",
]


def run_operation(tmp_path: Path, alias: str, macro: str, args: dict) -> subprocess.CompletedProcess:
    (tmp_path / "profiles.yml").write_text(devenv.render_profile("sample_product", alias, CONFIG))
    return subprocess.run(
        ["dbt", "-q", "run-operation", macro, "--args", json.dumps(args),
         "--profiles-dir", str(tmp_path), "--target-path", str(tmp_path / "target"),
         "--log-path", str(tmp_path / "logs")],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=180,
    )


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("pe", ["sample_product__pe", "sample_product__pe__src_clone", "sample_product__pe__staging"]),
        ("pehe", ["sample_product__pehe__staging"]),
        ("pe_he", ["sample_product__pe_he__staging"]),
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
    schemas = SCHEMAS + ["sample_product__mr", "sample_product__mr__v1", "sample_product__mrx__staging"]
    result = run_mr_operation(tmp_path, "mr", {"dry_run": True, "schemas": schemas})
    assert result.returncode == 0, result.stdout + result.stderr
    listed = [line.strip() for line in result.stdout.splitlines() if line.startswith("  ")]
    assert listed == ["sample_product__mr", "sample_product__mr__staging", "sample_product__mr__v1"]


def test_mr_drop_refuses_prod_target(tmp_path):
    result = run_mr_operation(tmp_path, "prod", {"dry_run": True, "schemas": SCHEMAS})
    assert result.returncode != 0
    assert "only runs in target 'mr'" in result.stdout + result.stderr
