"""dbtp init: rename the data product, fill in the team's dev settings and databricks.yml."""

import itertools

import pytest
import yaml

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

BUNDLE = '''# Replace the <placeholders>.
bundle:
  name: sample_product

variables:
  schedule:
    description: Quartz cron expression for the scheduled run (prod only).
    default: "0 0 5 * * ?"

targets:
  # Product dev
  dev:
    workspace:
      host: https://<dev-workspace-host>
      root_path: /Workspace/${bundle.name}
    variables:
      catalog: <product_dev_catalog>
      warehouse_id: <product-dev-sql-warehouse-id>
      service_principal: <product-dev-service-principal-application-id>

  # Product prod
  prod:
    workspace:
      host: https://<prod-workspace-host>
    variables:
      catalog: <product_prod_catalog>  # the prod catalog
      warehouse_id: <product-prod-sql-warehouse-id>
      service_principal: <product-prod-service-principal-application-id>
'''

ALL_OPTIONS = [
    "--server-hostname", "dbc-dev.cloud.databricks.com", "--warehouse-id", "teamwh",
    "--team-catalog", "team_x", "--product-dev-catalog", "orders_dev",
    "--product-dev-warehouse-id", "devwh", "--product-dev-service-principal", "dev-sp-id",
    "--prod-server-hostname", "https://dbc-prod.cloud.databricks.com/", "--product-prod-catalog",
    "orders_prod", "--product-prod-warehouse-id", "/sql/1.0/warehouses/prodwh",
    "--product-prod-service-principal", "prod-sp-id", "--prod-schedule", "0 30 6 * * ?",
]


def bundle_of(project):
    return yaml.safe_load((project.root / "databricks.yml").read_text())


def answering(monkeypatch, *answers):
    """Answer the questions in order, then Enter for every question after them."""
    prompts = []
    queue = itertools.chain(answers, itertools.repeat(""))

    def answer(prompt):
        prompts.append(prompt)
        return next(queue)

    monkeypatch.setattr("builtins.input", answer)
    return prompts


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
    prompts = answering(monkeypatch)
    assert init_product.main(project, {}, assume_yes=False) == 0
    host_prompt = next(p for p in prompts if p.startswith("Server hostname"))
    assert host_prompt.endswith("[dbc-x.cloud.databricks.com]: ")
    assert 'host = "https://dbc-x.cloud.databricks.com"\n' in project.dev_config.read_text()


def test_interactive_asks_again_after_an_invalid_answer(project, monkeypatch, capsys):
    answering(monkeypatch, "orders", "not a host", "dbc-x.cloud.databricks.com",
              "<id>", "/sql/1.0/warehouses/abc123", "team_y", "")
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
    answering(monkeypatch, "orders", "https://adb-2.net", "wh2", "team_y", "")
    assert init_product.main(project, {}, assume_yes=False) == 0
    assert devenv.read_dev_config(project.dev_config).team_catalog == "team_y"
    assert "<product_dev_catalog>" in project.dev_config.read_text()  # left for later


def test_cli_fills_every_placeholder_from_options(project, monkeypatch, capsys):
    monkeypatch.chdir(project.root)
    assert cli.main(["init", *ALL_OPTIONS, "--yes"]) == 0
    targets = bundle_of(project)["targets"]
    assert targets["dev"]["workspace"]["host"] == "https://dbc-dev.cloud.databricks.com"
    assert targets["dev"]["variables"] == {
        "catalog": "orders_dev", "warehouse_id": "devwh", "service_principal": "dev-sp-id"}
    assert targets["prod"]["workspace"]["host"] == "https://dbc-prod.cloud.databricks.com"
    assert targets["prod"]["variables"] == {
        "catalog": "orders_prod", "warehouse_id": "prodwh", "service_principal": "prod-sp-id"}
    assert bundle_of(project)["variables"]["schedule"]["default"] == "0 30 6 * * ?"
    text = (project.root / "databricks.yml").read_text()
    assert "<" not in text.split("\n", 1)[1]  # only the comment on the first line mentions them
    for comment in ("# Product prod", "  # the prod catalog", "description: Quartz cron"):
        assert comment in text
    assert 'default: "0 30 6 * * ?"' in text  # stays quoted
    assert init_product.placeholders_left(project) == []
    assert "Still to fill in" not in capsys.readouterr().out


def test_yes_fills_placeholders_with_their_defaults(project):
    assert init_product.main(project, {"host": "dbc-dev.cloud.databricks.com",
                                       "warehouse_id": "teamwh"}, assume_yes=True) == 0
    targets = bundle_of(project)["targets"]
    assert targets["dev"]["variables"]["warehouse_id"] == "teamwh"       # = team warehouse
    assert targets["prod"]["workspace"]["host"] == "https://dbc-dev.cloud.databricks.com"
    assert targets["prod"]["variables"]["warehouse_id"] == "teamwh"      # = product dev warehouse
    assert targets["prod"]["variables"]["catalog"] == "<product_prod_catalog>"
    assert bundle_of(project)["variables"]["schedule"]["default"] == "0 0 5 * * ?"


def test_yes_keeps_filled_values_over_defaults(project):
    init_product.main(project, {"host": "dbc-dev.cloud.databricks.com",
                                "prod_host": "dbc-prod.cloud.databricks.com"}, assume_yes=True)
    init_product.main(project, {"host": "dbc-new.cloud.databricks.com"}, assume_yes=True)
    targets = bundle_of(project)["targets"]
    assert targets["dev"]["workspace"]["host"] == "https://dbc-new.cloud.databricks.com"
    assert targets["prod"]["workspace"]["host"] == "https://dbc-prod.cloud.databricks.com"


def test_rerun_changes_filled_values(project, monkeypatch):
    monkeypatch.chdir(project.root)
    assert cli.main(["init", *ALL_OPTIONS, "--yes"]) == 0
    assert cli.main(["init", "--server-hostname", "dbc-new.cloud.databricks.com",
                     "--product-dev-catalog", "orders_dev2", "--product-prod-catalog", "p2",
                     "--product-prod-service-principal", "sp2", "--yes"]) == 0
    targets = bundle_of(project)["targets"]
    assert targets["dev"]["workspace"]["host"] == "https://dbc-new.cloud.databricks.com"
    assert targets["dev"]["variables"]["catalog"] == "orders_dev2"
    assert targets["prod"]["variables"]["catalog"] == "p2"
    assert targets["prod"]["variables"]["service_principal"] == "sp2"
    # The dev target keeps agreeing with config/dev-environment.toml.
    config = devenv.read_dev_config(project.dev_config)
    assert config.host == "https://dbc-new.cloud.databricks.com"
    assert devenv.read_product_dev_catalog(project.dev_config) == "orders_dev2"


def test_interactive_defaults_follow_the_answers(project, monkeypatch):
    prompts = answering(monkeypatch, "", "dbc-dev.cloud.databricks.com", "teamwh", "team_x",
                        "orders_dev")
    assert init_product.main(project, {}, assume_yes=False) == 0
    by_start = {prompt.split(" (")[0].split(" [")[0]: prompt for prompt in prompts}
    assert by_start["SQL warehouse ID for the product dev job"].endswith("[teamwh]: ")
    assert by_start["Server hostname of the prod workspace"].endswith(
        "[dbc-dev.cloud.databricks.com]: ")
    assert by_start["SQL warehouse ID for the product prod job"].endswith("[teamwh]: ")
    assert by_start["Prod schedule"].endswith("[0 0 5 * * ?]: ")


def test_rerun_shows_current_bundle_values(project, monkeypatch):
    monkeypatch.chdir(project.root)
    assert cli.main(["init", *ALL_OPTIONS, "--yes"]) == 0
    prompts = answering(monkeypatch)
    assert init_product.main(project, {}, assume_yes=False) == 0
    assert any(p.startswith("Product prod identity") and p.endswith("[prod-sp-id]: ")
               for p in prompts)
    assert any(p.startswith("Server hostname of the prod workspace")
               and p.endswith("[dbc-prod.cloud.databricks.com]: ") for p in prompts)


def test_left_for_later_keeps_placeholders_and_lists_them(project, monkeypatch, capsys):
    answering(monkeypatch, "", "dbc-dev.cloud.databricks.com", "teamwh", "team_x")
    assert init_product.main(project, {}, assume_yes=False) == 0
    targets = bundle_of(project)["targets"]
    assert targets["dev"]["variables"]["service_principal"] == (
        "<product-dev-service-principal-application-id>")
    out = capsys.readouterr().out
    assert "Still to fill in" in out
    assert ("config/dev-environment.toml: catalogs.product_dev = <product_dev_catalog>  "
            "(--product-dev-catalog)") in out
    assert ("databricks.yml: targets.prod.variables.service_principal = "
            "<product-prod-service-principal-application-id>  "
            "(--product-prod-service-principal)") in out
    assert "targets.prod.variables.catalog = <product_prod_catalog>  (--product-prod-catalog)" in out
    assert "targets.dev.variables.warehouse_id" not in out  # filled with the team warehouse


@pytest.mark.parametrize(("option", "value"), [
    ("--prod-server-hostname", "not a host"), ("--product-prod-catalog", "<x>"),
    ("--product-dev-service-principal", 'a"b'), ("--product-prod-warehouse-id", "a-b"),
    ("--prod-schedule", "daily"),
])
def test_invalid_deployment_values_are_refused(project, monkeypatch, option, value):
    monkeypatch.chdir(project.root)
    with pytest.raises(SystemExit):
        cli.main(["init", option, value, "--yes"])
    assert (project.root / "databricks.yml").read_text() == BUNDLE
