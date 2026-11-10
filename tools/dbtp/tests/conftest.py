import os
import stat

import pytest


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    """Put a fake executable on PATH: fake_bin("dbt", "<sh script>")."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def make(name: str, script: str):
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + script)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    return make
