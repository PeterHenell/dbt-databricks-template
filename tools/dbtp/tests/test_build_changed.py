"""`dbtp build-changed` download step, against a fake `databricks` CLI on PATH."""

import os
import stat

import pytest

from dbtp import build_changed
from dbtp.devenv import SetupError

HOST = "https://adb-1.2.azuredatabricks.net"


def fake_cli(tmp_path, monkeypatch, script: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "databricks"
    cli.write_text("#!/bin/sh\n" + script)
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return tmp_path / "calls"


def test_downloads_latest_manifest_with_developer_login(tmp_path, monkeypatch):
    calls = fake_cli(tmp_path, monkeypatch, f"""
echo "$@ HOST=$DATABRICKS_HOST CONFIG=$DATABRICKS_CONFIG_FILE" > {tmp_path}/calls
for last; do :; done
echo '{{"metadata": {{}}}}' > "$last"
""")
    target = build_changed.download_manifest(HOST, "orders_dev", tmp_path / "state")
    assert target.read_text().startswith('{"metadata"')
    assert calls.read_text().strip().startswith(
        "fs cp --overwrite dbfs:/Volumes/orders_dev/_dbt_artifacts/state/latest/manifest.json"
    )
    assert f"HOST={HOST} CONFIG=" in calls.read_text()


def test_download_uses_profile_and_keeps_config_file_visible(tmp_path, monkeypatch):
    # With `auth_storage = secure` the CLI must read ~/.databrickscfg to find the keyring.
    config = tmp_path / "databrickscfg"
    config.write_text(f"[__settings__]\nauth_storage = secure\n\n[DEFAULT]\nhost = {HOST}\n")
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(config))
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "other-workspace")
    calls = fake_cli(tmp_path, monkeypatch, f"""
echo "$@ CONFIG=$DATABRICKS_CONFIG_FILE PROFILE_ENV=$DATABRICKS_CONFIG_PROFILE" > {tmp_path}/calls
for last; do :; done
echo '{{}}' > "$last"
""")
    build_changed.download_manifest(HOST, "orders_dev", tmp_path / "state", "DEFAULT")
    call = calls.read_text()
    assert call.startswith("fs cp --profile DEFAULT --overwrite ")
    assert f"CONFIG={config} " in call
    assert os.devnull not in call
    assert call.rstrip().endswith("PROFILE_ENV=")


def test_clear_error_when_no_product_dev_run_yet(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, 'echo "Error: file does not exist" >&2; exit 1\n')
    with pytest.raises(SetupError, match="No product dev manifest"):
        build_changed.download_manifest(HOST, "orders_dev", tmp_path / "state")


def test_other_errors_are_shown(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, 'echo "Error: permission denied" >&2; exit 1\n')
    with pytest.raises(SetupError, match="permission denied"):
        build_changed.download_manifest(HOST, "orders_dev", tmp_path / "state")


def test_dbt_command_defers_to_downloaded_state(tmp_path):
    assert build_changed.dbt_command(tmp_path, ["--exclude", "published"]) == [
        "dbt", "build", "--select", "state:modified+", "--defer", "--state", str(tmp_path),
        "--exclude", "published",
    ]
