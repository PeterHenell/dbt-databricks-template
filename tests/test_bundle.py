"""The bundle, the deployment profile and the CI config: consistency and an offline validate.

`test_bundle_validates_against_mock_workspace` runs the real Databricks CLI against a
fake workspace API (tests/mock_databricks.py), on a copy of the repository with the
<placeholders> filled in. It is skipped when the CLI isn't installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

import devenv
from mock_databricks import MockWorkspace

ROOT = devenv.REPO_ROOT


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def locked_versions() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return {package["name"]: package["version"] for package in lock["package"]}


def test_bundle_name_is_the_product():
    assert load("databricks.yml")["bundle"]["name"] == devenv.read_product()


def test_every_profile_is_named_after_the_product():
    product = devenv.read_product()
    for path in ("deploy/profiles.yml", "local/profiles.yml"):
        assert list(load(path)) == [product], f"{path}: top-level key must be the product name"


def test_job_environment_pins_match_uv_lock():
    locked = locked_versions()
    environments = load("resources/dbt_job.yml")["resources"]["jobs"]["dbt_build"]["environments"]
    pins = [dep for env in environments for dep in env["spec"]["dependencies"]]
    assert pins, "the job environments pin no packages"
    for pin in pins:
        name, version = pin.split("==")
        assert locked[name] == version, f"{pin} differs from uv.lock ({locked[name]})"


def test_dev_target_agrees_with_dev_environment_config():
    config = tomllib.loads((ROOT / "config" / "dev-environment.toml").read_text())
    dev = load("databricks.yml")["targets"]["dev"]
    assert dev["workspace"]["host"].rstrip("/") == config["databricks"]["host"].rstrip("/")
    assert dev["variables"]["catalog"] == config["catalogs"]["product_dev"]


def test_only_prod_has_a_schedule():
    targets = load("databricks.yml")["targets"]
    assert "resources" not in targets["dev"]
    assert "schedule" in targets["prod"]["resources"]["jobs"]["dbt_build"]
    assert "schedule" not in load("resources/dbt_job.yml")["resources"]["jobs"]["dbt_build"]


def test_deploy_profile_targets():
    product = devenv.read_product()
    outputs = load("deploy/profiles.yml")[product]["outputs"]
    assert set(outputs) == {"prod", "mr"}
    assert outputs["mr"]["schema"] == f"{product}__mr"
    for output in outputs.values():
        # No environment-specific values in the profile (ADR 0008).
        assert "{{" in output["host"] and "{{" in output["catalog"] and "{{" in output["http_path"]
        assert "client_secret" not in output


def test_gitlab_ci_jobs_only_call_make():
    ci = load(".gitlab-ci.yml")
    for name, job in ci.items():
        if not isinstance(job, dict):
            continue
        for key in ("before_script", "script", "after_script"):
            for line in job.get(key, []):
                assert line.startswith("make "), f"{name}.{key}: {line!r} is not a make target"


def test_gitlab_ci_resource_groups_and_manual_prod():
    ci = load(".gitlab-ci.yml")
    assert ci["mr-build"]["resource_group"] == "mr-build"
    assert ci["product-dev"]["resource_group"] == "product-dev"
    assert ci["deploy-prod"]["resource_group"] == "product-prod"
    assert ci["deploy-prod"]["environment"]["name"] == "prod"
    assert ci["deploy-prod"]["rules"] == [{"if": "$CI_COMMIT_TAG", "when": "manual"}]
    assert "bundle-run" not in " ".join(ci["deploy-prod"]["script"])  # the schedule takes over


def test_main_pipeline_deploys_nothing():
    ci = load(".gitlab-ci.yml")
    deploying = [name for name, job in ci.items() if isinstance(job, dict)
                 and any("bundle-deploy" in line or "ci-mr-build" in line for line in job.get("script", []))]
    for name in deploying:
        rules = ci[name].get("rules") or [r for parent in ci[name]["extends"] for r in ci[parent].get("rules", [])]
        assert all("CI_DEFAULT_BRANCH" not in rule.get("if", "") for rule in rules), name


def test_ci_tools_pins_come_from_the_dev_container():
    dockerfile = (ROOT / ".devcontainer" / "Dockerfile").read_text()
    assert re.search(r"^ARG UV_VERSION=\S+$", dockerfile, re.M)
    assert re.search(r"^ARG DATABRICKS_CLI_VERSION=\S+$", dockerfile, re.M)


def dbt_ls(target: str, tmp_path: Path) -> list[dict]:
    env = {**os.environ, "DBT_HOST": "adb-1.azuredatabricks.net", "DBT_ACCESS_TOKEN": "unused"}
    result = subprocess.run(
        ["dbt", "-q", "ls", "--profiles-dir", "deploy", "--target", target,
         "--vars", "{deploy_catalog: cat_x, deploy_warehouse_id: wh1}",
         "--resource-type", "model", "--output", "json", "--output-keys", "name database schema",
         "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


@pytest.mark.parametrize(("target", "prefix"), [("prod", ""), ("mr", "sample_product__mr__")])
def test_deploy_profile_schema_names(tmp_path, target, prefix):
    nodes = dbt_ls(target, tmp_path)
    assert {node["database"] for node in nodes} == {"cat_x"}
    assert {node["schema"] for node in nodes} == {
        prefix + layer for layer in ("staging", "intermediate", "v1", "v2")}


@pytest.mark.skipif(shutil.which("databricks") is None, reason="Databricks CLI not installed")
@pytest.mark.parametrize("target", ["dev", "prod"])
def test_bundle_validates_against_mock_workspace(tmp_path, target):
    for name in ("databricks.yml", "resources", "deploy", "scripts", "dbt_project.yml"):
        source = ROOT / name
        (shutil.copytree if source.is_dir() else shutil.copy)(source, tmp_path / name)
    with MockWorkspace() as workspace:
        bundle = (tmp_path / "databricks.yml").read_text()
        bundle = re.sub(r"https://<[a-z-]+-host>", workspace.url, bundle)
        (tmp_path / "databricks.yml").write_text(re.sub(r"<([a-z_-]+)>", r"\1", bundle))
        env = {key: value for key, value in os.environ.items() if not key.startswith("DATABRICKS_")}
        env.update(DATABRICKS_CONFIG_FILE=os.devnull, DATABRICKS_HOST=workspace.url, DATABRICKS_TOKEN="x")
        result = subprocess.run(["databricks", "bundle", "validate", "-t", target, "-o", "json"],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    job = config["resources"]["jobs"]["dbt_build"]
    catalog = f"product_{target}_catalog"
    dbt, publish = job["tasks"]
    assert dbt["dbt_task"]["profiles_directory"] == "deploy"
    assert f"deploy_catalog: {catalog}" in dbt["dbt_task"]["commands"][0]
    assert publish["depends_on"] == [{"task_key": "dbt_build"}]
    assert f"/Volumes/{catalog}/_dbt_artifacts/state" in publish["spark_python_task"]["parameters"]
    assert config["resources"]["volumes"]["dbt_artifacts_state"]["catalog_name"] == catalog
    assert job["run_as"]["service_principal_name"] == f"product-{target}-service-principal-application-id"
    assert ("schedule" in job) == (target == "prod")
