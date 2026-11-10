"""dbtp.mr_build: commands, token hand-over to dbt, failure handling (no Databricks)."""

from __future__ import annotations

import pytest

from dbtp import devenv, mr_build
from dbtp.devenv import Project, SetupError

CONFIG = devenv.DevConfig("https://adb-1.2.azuredatabricks.net", "wh1", "team_x")


class FakeConfig:
    def __init__(self, host):
        self.host = host

    def authenticate(self):
        return {"Authorization": "Bearer tok-123"}


def test_access_token_from_sdk_config():
    assert mr_build.access_token("https://h", FakeConfig) == "tok-123"


def test_access_token_failure_is_a_setup_error():
    class Broken:
        def __init__(self, host):
            raise ValueError("no credentials")

    with pytest.raises(SetupError, match="no credentials"):
        mr_build.access_token("https://h", Broken)


def test_commands_drop_then_full_build_without_defer():
    deps, drop, build = mr_build.commands(CONFIG, ["--fail-fast"])
    assert deps == ["dbt", "deps"]
    assert drop[:3] == ["dbt", "run-operation", "drop_mr_environment"]
    assert "{dry_run: false}" in drop
    for command in (drop, build):
        assert command[command.index("--target") + 1] == "mr"
        assert command[command.index("--profiles-dir") + 1] == "deploy"
        assert '"deploy_catalog": "team_x"' in command[command.index("--vars") + 1]
    assert build[:2] == ["dbt", "build"] and build[-1] == "--fail-fast"
    assert "--defer" not in build and "--state" not in build


def test_main_passes_token_and_stops_at_first_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(devenv, "read_dev_config", lambda path: CONFIG)
    calls = []

    def run(command, project, env):
        calls.append((command[1], env["DBT_HOST"], env["DBT_ACCESS_TOKEN"]))
        return 1 if command[1] == "run-operation" else 0

    assert mr_build.main(Project(tmp_path), [], config_factory=FakeConfig, run=run) == 1
    assert calls == [("deps", "adb-1.2.azuredatabricks.net", "tok-123"),
                     ("run-operation", "adb-1.2.azuredatabricks.net", "tok-123")]
