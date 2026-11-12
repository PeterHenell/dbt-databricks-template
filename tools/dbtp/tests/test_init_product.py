"""dbtp init: rename the data product and fill in the team's dev settings."""

import pytest

from dbtp import cli, devenv, init_product
from dbtp.devenv import Project, SetupError

DEV_CONFIG = '''# Team settings
[databricks]
# Dev workspace URL
host = "https://<dev-workspace-host>"
warehouse_id = "<shared-dev-sql-warehouse-id>"

[catalogs]
team = "<team_catalog>"
product_dev = "<product_dev_catalog>"
'''

BUNDLE = '''bundle:
  name: sample_product
targets:
  dev:
    workspace:
      host: https://<dev-workspace-host>
    variables:
      catalog: <product_dev_catalog>
  prod:
    workspace:
      host: https://<prod-workspace-host>
    variables:
      catalog: <product_prod_catalog>
'''


@pytest.fixture
def project(tmp_path):
    (tmp_path / "dbt_project.yml").write_text(
        "name: sample_product\nprofile: sample_product\nmodels:\n  sample_product:\n    +x: 1\n")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "profiles.yml").write_text(
        "sample_product:\n  outputs:\n    mr:\n      schema: sample_product__mr\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "dev-environment.toml").write_text(DEV_CONFIG)
    (tmp_path / "databricks.yml").write_text(BUNDLE)
    return Project.at(tmp_path)


def test_rename_in_text_matches_whole_names_and_schema_prefixes():
    text = "sample_product:\nschema: sample_product__mr\nx: sample_products\ny: my_sample_product"
    assert init_product.rename_in_text(text, "sample_product", "orders") == (
        "orders:\nschema: orders__mr\nx: sample_products\ny: my_sample_product")


def test_init_renames_product_and_fills_settings(project):
    changed = init_product.apply(project, init_product.Settings(
        product="customer_orders", host="https://adb-1.azuredatabricks.net/",
        warehouse_id="wh1", team_catalog="team_x", product_dev_catalog="orders_dev"))

    assert sorted(changed) == ["config/dev-environment.toml", "databricks.yml",
                               "dbt_project.yml", "deploy/profiles.yml"]
    assert devenv.read_product(project.dbt_project) == "customer_orders"
    assert "  customer_orders:\n" in project.dbt_project.read_text()
    assert "schema: customer_orders__mr" in (project.root / "deploy/profiles.yml").read_text()
    config = devenv.read_dev_config(project.dev_config)
    assert (config.host, config.warehouse_id, config.team_catalog) == (
        "https://adb-1.azuredatabricks.net", "wh1", "team_x")
    assert devenv.read_product_dev_catalog(project.dev_config) == "orders_dev"
    assert "# Dev workspace URL" in project.dev_config.read_text()  # comments kept
    bundle = (project.root / "databricks.yml").read_text()
    assert "name: customer_orders" in bundle
    assert "host: https://adb-1.azuredatabricks.net\n" in bundle
    assert "catalog: orders_dev" in bundle
    assert "<prod-workspace-host>" in bundle and "<product_prod_catalog>" in bundle  # prod untouched


def test_init_can_rename_again(project):
    init_product.apply(project, init_product.Settings(product="first_name"))
    init_product.apply(project, init_product.Settings(product="second_name"))
    assert devenv.read_product(project.dbt_project) == "second_name"
    assert "schema: second_name__mr" in (project.root / "deploy/profiles.yml").read_text()


def test_values_not_given_are_left_alone(project):
    changed = init_product.apply(project, init_product.Settings(product="sample_product"))
    assert changed == []
    assert project.dev_config.read_text() == DEV_CONFIG


@pytest.mark.parametrize(("field", "value"), [
    ("product", "Orders"), ("product", "my__orders"), ("product", "orders-x"),
    ("host", "not a host"), ("host", "<dev-workspace-host>"), ("host", "https://<dev-workspace-host>"),
    ("host", "localhost"), ("team_catalog", ""), ("warehouse_id", "<id>"), ("warehouse_id", ""),
    ("warehouse_id", "/sql/1.0/warehouses/"),
])
def test_invalid_values_are_refused(project, field, value):
    settings = init_product.Settings(product="orders")
    setattr(settings, field, value)
    with pytest.raises(SetupError):
        init_product.apply(project, settings)
    assert devenv.read_product(project.dbt_project) == "sample_product"


@pytest.mark.parametrize("value", [
    "dbc-x.cloud.databricks.com",
    "https://dbc-x.cloud.databricks.com/",
    "http://dbc-x.cloud.databricks.com",
    "https://dbc-x.cloud.databricks.com/sql/warehouses/abc?o=1",
    "  DBC-X.cloud.databricks.com  ",
])
def test_server_hostname_is_accepted_as_pasted_from_the_ui(project, value):
    init_product.apply(project, init_product.Settings(product="sample_product", host=value))
    assert 'host = "https://dbc-x.cloud.databricks.com"\n' in project.dev_config.read_text()
    assert "host: https://dbc-x.cloud.databricks.com\n" in (project.root / "databricks.yml").read_text()


@pytest.mark.parametrize("value", [
    "9f612f879c29d440",
    "/sql/1.0/warehouses/9f612f879c29d440",
    "https://dbc-x.cloud.databricks.com/sql/warehouses/9f612f879c29d440?o=1",
])
def test_warehouse_id_is_accepted_as_pasted_from_the_ui(project, value):
    init_product.apply(project, init_product.Settings(product="sample_product", warehouse_id=value))
    assert 'warehouse_id = "9f612f879c29d440"' in project.dev_config.read_text()


@pytest.mark.parametrize("option", ["--host", "--server-hostname"])
def test_host_and_server_hostname_options_are_the_same(project, monkeypatch, option):
    monkeypatch.chdir(project.root)
    assert cli.main(["init", option, "dbc-x.cloud.databricks.com", "--yes"]) == 0
    assert 'host = "https://dbc-x.cloud.databricks.com"' in project.dev_config.read_text()


def test_rerun_shows_the_hostname_without_scheme(project, monkeypatch):
    init_product.apply(project, init_product.Settings(
        product="sample_product", host="https://dbc-x.cloud.databricks.com"))
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", answer)
    assert init_product.main(project, {}, assume_yes=False) == 0
    host_prompt = next(p for p in prompts if p.startswith("Server hostname"))
    assert host_prompt.endswith("[dbc-x.cloud.databricks.com]: ")
    assert 'host = "https://dbc-x.cloud.databricks.com"\n' in project.dev_config.read_text()


def test_interactive_asks_again_after_an_invalid_answer(project, monkeypatch, capsys):
    answers = iter(["orders", "not a host", "dbc-x.cloud.databricks.com",
                    "<id>", "/sql/1.0/warehouses/abc123", "team_y", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert init_product.main(project, {}, assume_yes=False) == 0
    config = devenv.read_dev_config(project.dev_config)
    assert (config.host, config.warehouse_id) == ("https://dbc-x.cloud.databricks.com", "abc123")
    out = capsys.readouterr().out
    assert "is not a server hostname" in out and "is not a SQL warehouse ID" in out


def test_cli_non_interactive(project, monkeypatch, capsys):
    monkeypatch.chdir(project.root)
    assert cli.main(["init", "--product", "orders", "--team-catalog", "team_x", "--yes"]) == 0
    assert devenv.read_product(project.dbt_project) == "orders"
    assert 'team = "team_x"' in project.dev_config.read_text()
    assert 'warehouse_id = "<shared-dev-sql-warehouse-id>"' in project.dev_config.read_text()
    assert "Data product: orders" in capsys.readouterr().out


def test_interactive_questions_default_to_current_values(project, monkeypatch):
    answers = iter(["orders", "https://adb-2.net", "wh2", "team_y", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert init_product.main(project, {}, assume_yes=False) == 0
    assert devenv.read_dev_config(project.dev_config).team_catalog == "team_y"
    assert "<product_dev_catalog>" in project.dev_config.read_text()  # left for later
