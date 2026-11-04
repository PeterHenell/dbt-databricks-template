import pytest

import devenv
import setup_dev

CONFIG = devenv.DevConfig(
    host="https://adb-123.4.azuredatabricks.net",
    warehouse_id="abc123",
    team_catalog="team_x",
)


@pytest.mark.parametrize(
    ("first", "last", "alias"),
    [
        ("Peter", "Henell", "pehe"),
        ("Åsa", "Öberg", "asob"),
        ("Søren", "Kierkegaard", "soki"),
        ("José", "Ñúñez", "jonu"),
        ("Jo", "O'Neil", "joon"),
    ],
)
def test_suggest_alias(first, last, alias):
    assert devenv.suggest_alias(first, last) == alias


def test_split_display_name():
    assert devenv.split_display_name("Peter Henell") == ("Peter", "Henell")
    assert devenv.split_display_name("Anna Maria von Berg") == ("Anna", "Berg")
    assert devenv.split_display_name("Prince") == ("Prince", "")


@pytest.mark.parametrize("alias", ["pehe", "pe", "pe_he", "dev2"])
def test_valid_aliases(alias):
    assert devenv.validate_alias(alias) is None


@pytest.mark.parametrize("alias", ["", "Pehe", "pe__he", "_pe", "pe_", "pe-he", "pö", "mr"])
def test_invalid_aliases(alias):
    assert devenv.validate_alias(alias) is not None


def test_profile_round_trip(tmp_path):
    path = tmp_path / "profiles.yml"
    path.write_text(devenv.render_profile("orders", "pehe", CONFIG))
    assert devenv.alias_from_profile("orders", path) == "pehe"


def test_rendered_profile_fields(tmp_path):
    import yaml

    output = yaml.safe_load(devenv.render_profile("orders", "pehe", CONFIG))["orders"]
    assert output["target"] == "dev"
    dev = output["outputs"]["dev"]
    assert dev == {
        "type": "databricks",
        "host": "adb-123.4.azuredatabricks.net",
        "http_path": "/sql/1.0/warehouses/abc123",
        "catalog": "team_x",
        "schema": "orders__pehe",
        "auth_type": "oauth",
        "threads": 8,
    }


def test_hand_edited_alias_is_read_back(tmp_path):
    path = tmp_path / "profiles.yml"
    path.write_text(devenv.render_profile("orders", "pehe", CONFIG).replace("orders__pehe", "orders__peter"))
    assert devenv.alias_from_profile("orders", path) == "peter"


def test_missing_or_foreign_profile_has_no_alias(tmp_path):
    path = tmp_path / "profiles.yml"
    assert devenv.alias_from_profile("orders", path) is None
    path.write_text("other:\n  outputs:\n    dev:\n      schema: x\n")
    assert devenv.alias_from_profile("orders", path) is None


def test_existing_alias_is_the_default(monkeypatch):
    # Pressing enter keeps the hand-edited alias rather than the suggestion.
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert setup_dev.choose_alias("pehe", "peter", None, False) == "peter"


def test_empty_alias_is_refused_until_valid(monkeypatch):
    answers = iter(["", "pehe"])  # no suggestion and an empty answer -> asked again
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert setup_dev.choose_alias("", None, None, False) == "pehe"


def test_non_interactive_without_alias_fails():
    with pytest.raises(devenv.SetupError):
        setup_dev.choose_alias("", None, None, True)


def test_placeholders_are_rejected(tmp_path):
    path = tmp_path / "dev.toml"
    path.write_text(
        '[databricks]\nhost = "https://<dev-workspace-host>"\nwarehouse_id = "x"\n[catalogs]\nteam = "t"\n'
    )
    with pytest.raises(devenv.SetupError, match="placeholders"):
        devenv.read_dev_config(path)


def test_project_name_matches_profile():
    assert devenv.read_product() == "sample_product"
