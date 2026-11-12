"""dbtp bundle refuses a target that still has template <placeholders>."""

import pytest

from dbtp import bundle, cli, devenv

BUNDLE = '''# Replace the <placeholders>.
bundle:
  name: orders
targets:
  dev:
    workspace:
      host: https://dbc-dev.cloud.databricks.com
    variables:
      catalog: orders_dev
  prod:
    workspace:
      host: https://<prod-workspace-host>
    variables:
      catalog: <product_prod_catalog>
      root: ${var.catalog}
'''


@pytest.fixture
def project(tmp_path, monkeypatch, fake_bin):
    (tmp_path / "dbt_project.yml").write_text("name: orders\nprofile: orders\n")
    (tmp_path / "databricks.yml").write_text(BUNDLE)
    artifact = tmp_path / "target" / "release" / "bundle"
    artifact.mkdir(parents=True)
    (artifact / "databricks.yml").write_text(BUNDLE)
    monkeypatch.setattr(bundle.release, "bundle_dir", lambda project: artifact)
    monkeypatch.delenv(devenv.PROJECT_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    calls = tmp_path / "calls"
    fake_bin("databricks", f'echo "$@" >> {calls}\n')
    return calls


@pytest.mark.parametrize("action", ["validate", "deploy", "run"])
def test_target_with_placeholders_is_refused_before_the_cli(project, capsys, action):
    with pytest.raises(SystemExit):
        cli.main(["bundle", action, "-t", "prod"])
    err = capsys.readouterr().err
    assert "target 'prod' still has template placeholders" in err
    assert "targets.prod.workspace.host: https://<prod-workspace-host>" in err
    assert "targets.prod.variables.catalog: <product_prod_catalog>" in err
    assert "uv run dbtp init" in err
    assert not project.exists()  # the Databricks CLI never ran


@pytest.mark.parametrize("action", ["validate", "deploy", "run"])
def test_filled_target_runs_the_cli(project, action):
    assert cli.main(["bundle", action, "-t", "dev"]) == 0
    assert project.read_text().startswith(f"bundle {action} -t dev")


def test_placeholders_outside_targets_count_for_every_target():
    config = {"variables": {"x": {"default": "<fill-me>"}},
              "targets": {"dev": {"variables": {"catalog": "ok"}}}}
    assert bundle.target_placeholders(config, "dev") == [
        (("variables", "x", "default"), "<fill-me>")]
