"""Databricks CLI login lookup in `dbtp setup`, against a fake `databricks` CLI on PATH."""

import pytest

from dbtp import setup_dev
from dbtp.devenv import SetupError

HOST = "https://dbc-1234.cloud.databricks.com"
TOKEN_CLI = 'echo "$@" >> "$(dirname "$0")/../calls"; echo \'{"access_token": "tok"}\'\n'


@pytest.fixture
def cli_config(tmp_path, monkeypatch):
    """Write a fake ~/.databrickscfg and point the CLI (and dbtp) at it."""
    path = tmp_path / "databrickscfg"
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(path))

    def write(text: str):
        path.write_text(text)
        return path

    return write


def test_single_matching_profile(cli_config):
    cli_config(f"[DEFAULT]\nhost = https://other.cloud.databricks.com\n\n[dev]\nhost = {HOST}/\n")
    assert setup_dev.cli_profile(HOST) == "dev"


def test_host_comparison_ignores_case_and_trailing_slash(cli_config):
    cli_config(f"[dev]\nhost = {HOST.upper()}/\n")
    assert setup_dev.cli_profile(HOST + "/") == "dev"


def test_duplicate_profiles_prefer_default_profile(cli_config, capsys):
    cli_config(
        "[__settings__]\ndefault_profile = mine\nauth_storage = secure\n\n"
        f"[DEFAULT]\nhost = {HOST}\n\n[mine]\nhost = {HOST}\n"
    )
    assert setup_dev.cli_profile(HOST) == "mine"
    note = capsys.readouterr().out
    assert "'mine'" in note and "DEFAULT" in note


def test_duplicate_profiles_without_default_take_the_first(cli_config, capsys):
    cli_config(f"[DEFAULT]\nhost = {HOST}\n\n[dbc-1234]\nhost = {HOST}\n")
    assert setup_dev.cli_profile(HOST) == "DEFAULT"
    assert "dbc-1234" in capsys.readouterr().out


def test_default_profile_for_another_workspace_is_never_used(cli_config):
    cli_config(
        "[__settings__]\ndefault_profile = prod\n\n"
        "[prod]\nhost = https://prod.cloud.databricks.com\n\n"
        f"[a]\nhost = {HOST}\n\n[b]\nhost = {HOST}\n"
    )
    assert setup_dev.cli_profile(HOST) == "a"


def test_no_matching_profile_or_no_config(cli_config, tmp_path, monkeypatch):
    cli_config("[DEFAULT]\nhost = https://other.cloud.databricks.com\n")
    assert setup_dev.cli_profile(HOST) is None
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(tmp_path / "missing"))
    assert setup_dev.cli_profile(HOST) is None


def test_two_profiles_for_dev_host_setup_gets_token(cli_config, fake_bin, tmp_path):
    cli_config(f"[DEFAULT]\nhost = {HOST}\n\n[dbc-1234]\nhost = {HOST}\n")
    fake_bin("databricks", TOKEN_CLI)
    profile = setup_dev.cli_profile(HOST)
    assert setup_dev.cli_access_token(HOST, profile) == "tok"
    assert (tmp_path / "calls").read_text().strip() == "auth token --profile DEFAULT -o json"


def test_no_profile_falls_back_to_host(cli_config, fake_bin, tmp_path):
    cli_config("")
    fake_bin("databricks", TOKEN_CLI)
    assert setup_dev.cli_access_token(HOST, setup_dev.cli_profile(HOST)) == "tok"
    assert (tmp_path / "calls").read_text().strip() == f"auth token --host {HOST} -o json"


def test_cli_error_is_shown_with_login_hint(fake_bin):
    fake_bin(
        "databricks",
        'echo "Error: DEFAULT and dbc-1234 match https://dbc-1234 in ~/.databrickscfg" >&2\n'
        "exit 1\n",
    )
    with pytest.raises(SetupError) as error:
        setup_dev.cli_access_token(HOST, None)
    assert "DEFAULT and dbc-1234 match" in str(error.value)
    assert f"databricks auth login --host {HOST}" in str(error.value)
