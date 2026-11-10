"""dbtp.devenv (project discovery, settings, profile) and setup's alias choice."""

import pytest

from dbtp import devenv, setup_dev

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


def make_project(root, name="orders", profile="orders"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "dbt_project.yml").write_text(f"name: {name}\nprofile: {profile}\n")
    return root


def test_project_is_found_from_a_subdirectory(tmp_path, monkeypatch):
    monkeypatch.delenv(devenv.PROJECT_DIR_ENV, raising=False)
    root = make_project(tmp_path / "repo")
    (root / "models" / "staging").mkdir(parents=True)
    project = devenv.Project.find(root / "models" / "staging")
    assert project.root == root.resolve()
    assert project.product() == "orders"
    assert project.dev_config == root.resolve() / "config" / "dev-environment.toml"


def test_project_dir_env_wins(tmp_path, monkeypatch):
    root = make_project(tmp_path / "repo")
    monkeypatch.setenv(devenv.PROJECT_DIR_ENV, str(root))
    assert devenv.Project.find(tmp_path).root == root.resolve()


def test_no_project_is_a_setup_error(tmp_path, monkeypatch):
    monkeypatch.delenv(devenv.PROJECT_DIR_ENV, raising=False)
    with pytest.raises(devenv.SetupError, match="No dbt_project.yml"):
        devenv.Project.find(tmp_path)
    with pytest.raises(devenv.SetupError, match="not a data product repository"):
        devenv.Project.at(tmp_path)


def test_product_name_must_match_profile(tmp_path):
    root = make_project(tmp_path, name="orders", profile="other")
    with pytest.raises(devenv.SetupError, match="must both be"):
        devenv.Project(root).product()


def test_missing_dev_config_is_a_setup_error(tmp_path):
    with pytest.raises(devenv.SetupError, match="is missing"):
        devenv.read_dev_config(tmp_path / "dev-environment.toml")
