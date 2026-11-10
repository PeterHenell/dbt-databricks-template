"""`dbtp local …`: compose command choice, readiness wait, devcontainer guard."""

import pytest

from dbtp import local_engine
from dbtp.devenv import Project, SetupError


def test_compose_command_choice():
    file = ["-f", "local/compose.yml"]
    assert local_engine.compose_command({"COMPOSE_CMD": "podman compose"}) == ["podman", "compose", *file]
    assert local_engine.compose_command({}, which=lambda name: "/usr/bin/podman-compose") == [
        "podman-compose", *file]
    assert local_engine.compose_command({"COMPOSE_CMD": " "}, which=lambda name: None) == [
        "docker", "compose", *file]


def test_refuses_to_run_in_the_dev_container(tmp_path, monkeypatch):
    monkeypatch.setenv("DBT_DEVCONTAINER", "1")
    with pytest.raises(SetupError, match="on the host"):
        local_engine.up(Project(tmp_path))


def test_up_waits_for_the_metastore(tmp_path, fake_bin, monkeypatch):
    monkeypatch.delenv("DBT_DEVCONTAINER", raising=False)
    monkeypatch.setenv("COMPOSE_CMD", "fakecompose")
    # pg_isready fails twice, then succeeds.
    fake_bin("fakecompose", f"""
echo "$*" >> {tmp_path}/calls
case "$*" in *pg_isready*)
  n=$(cat {tmp_path}/n 2>/dev/null || echo 0); echo $((n+1)) > {tmp_path}/n; [ "$n" -ge 2 ] ;;
esac
""")
    sleeps = []
    assert local_engine.up(Project(tmp_path), sleep=sleeps.append) == 0
    calls = (tmp_path / "calls").read_text().splitlines()
    assert calls[:2] == ["-f local/compose.yml build dbt", "-f local/compose.yml up -d metastore-db"]
    assert len(calls) == 5 and sleeps == [1, 1]


def test_up_stops_when_compose_fails(tmp_path, fake_bin, monkeypatch):
    monkeypatch.delenv("DBT_DEVCONTAINER", raising=False)
    monkeypatch.setenv("COMPOSE_CMD", "fakecompose")
    fake_bin("fakecompose", "exit 3\n")
    with pytest.raises(SystemExit) as exit_info:
        local_engine.up(Project(tmp_path))
    assert exit_info.value.code == 3
