"""ci_tools.py: version pins and CPU architecture (no downloads)."""

import pytest

from dbtp import ci_tools


def test_pins_from_dockerfile(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM x\nARG UV_VERSION=0.11.25\nARG DATABRICKS_CLI_VERSION=1.19.0\n")
    assert ci_tools.pins(dockerfile) == ("0.11.25", "1.19.0")


def test_missing_pin_fails(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("ARG UV_VERSION=0.11.25\n")
    with pytest.raises(SystemExit, match="DATABRICKS_CLI_VERSION"):
        ci_tools.pins(dockerfile)


@pytest.mark.parametrize(("machine", "arch"), [("x86_64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")])
def test_cli_arch(machine, arch):
    assert ci_tools.cli_arch(machine) == arch


def test_installed_tools_are_not_reinstalled(tmp_path, monkeypatch):
    (tmp_path / "uv").write_text("#!/bin/sh\necho 'uv 0.11.25 (abc)'\n")
    (tmp_path / "databricks").write_text("#!/bin/sh\necho 'Databricks CLI v1.19.0'\n")
    for name in ("uv", "databricks"):
        (tmp_path / name).chmod(0o755)
    monkeypatch.setattr(ci_tools.subprocess, "run", ci_tools.subprocess.run)
    monkeypatch.setattr(ci_tools.urllib.request, "urlopen", lambda *a, **k: 1 / 0)
    ci_tools.install_uv(tmp_path, "0.11.25")
    ci_tools.install_databricks_cli(tmp_path, "1.19.0")
