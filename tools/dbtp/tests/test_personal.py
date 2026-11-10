"""`dbtp clean-dev` and `dbtp clone-sources` against a fake `dbt` on PATH."""

from dbtp import checks, personal
from dbtp.devenv import Project

# Prints the dry-run listing, and records the real drop.
FAKE_DBT = """
case "$*" in
  *"dry_run: true"*) printf 'Would drop:\\n  orders__pe\\n  orders__pe__staging\\n' ;;
  *"dry_run: false"*) echo dropped > "$CALLS" ;;
esac
"""


def test_clean_dev_drops_after_yes(tmp_path, fake_bin, monkeypatch, capsys):
    monkeypatch.setenv("CALLS", str(tmp_path / "calls"))
    fake_bin("dbt", FAKE_DBT)
    prompts = []
    assert personal.clean_dev(Project(tmp_path), ask=lambda q: prompts.append(q) or "yes") == 0
    assert "orders__pe__staging" in capsys.readouterr().out
    assert prompts == ["Type 'yes' to drop them: "]
    assert (tmp_path / "calls").read_text().strip() == "dropped"


def test_clean_dev_keeps_everything_without_yes(tmp_path, fake_bin, monkeypatch, capsys):
    monkeypatch.setenv("CALLS", str(tmp_path / "calls"))
    fake_bin("dbt", FAKE_DBT)
    assert personal.clean_dev(Project(tmp_path), ask=lambda q: "y") == 0
    assert "Nothing dropped." in capsys.readouterr().out
    assert not (tmp_path / "calls").exists()


def test_clean_dev_with_nothing_to_drop_does_not_ask(tmp_path, fake_bin):
    fake_bin("dbt", 'echo "Nothing to drop for orders__pe"\n')
    assert personal.clean_dev(Project(tmp_path), ask=lambda q: 1 / 0) == 0


def test_clean_dev_dry_run_failure_is_passed_on(tmp_path, fake_bin):
    fake_bin("dbt", 'echo "Refusing target prod"; exit 2\n')
    assert personal.clean_dev(Project(tmp_path), ask=lambda q: 1 / 0) == 2


def test_clone_sources_runs_the_macro(tmp_path, fake_bin):
    fake_bin("dbt", f'echo "$@" > {tmp_path}/calls\n')
    assert personal.clone_sources(Project(tmp_path)) == 0
    assert (tmp_path / "calls").read_text().strip() == "-q run-operation clone_sources"


def test_parse_uses_the_deploy_profile_without_credentials(tmp_path, fake_bin):
    fake_bin("dbt", f'echo "$DBT_HOST $DBT_ACCESS_TOKEN $*" > {tmp_path}/calls\n')
    assert checks.parse(Project(tmp_path)) == 0
    assert (tmp_path / "calls").read_text().strip() == (
        "parse.invalid unused parse --profiles-dir deploy --target mr "
        "--vars {deploy_catalog: parse, deploy_warehouse_id: parse}")
