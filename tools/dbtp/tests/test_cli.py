"""The `dbtp` command line: argument parsing and routing to the commands."""

import pytest

from dbtp import cli, devenv


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "dbt_project.yml").write_text("name: orders\nprofile: orders\n")
    monkeypatch.delenv(devenv.PROJECT_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def parse(*argv):
    return cli.build_parser().parse_args(argv)


def test_dbt_arguments_after_double_dash():
    args = parse("build-changed", "--", "--exclude", "published")
    assert cli.dbt_args(args.dbt_args) == ["--exclude", "published"]
    assert cli.dbt_args(parse("build-changed", "--").dbt_args) == []
    assert cli.dbt_args(parse("mr-build", "--", "--fail-fast").dbt_args) == ["--fail-fast"]


def test_local_dbt_takes_a_dbt_command():
    args = parse("local", "dbt", "build", "--select", "customers")
    assert cli.dbt_args(args.dbt_args) == ["build", "--select", "customers"]


@pytest.mark.parametrize(("argv", "module", "function", "expected"), [
    (["clone-sources"], "personal", "clone_sources", ()),
    (["clean-dev"], "personal", "clean_dev", ()),
    (["parse"], "checks", "parse", ()),
    (["local", "down"], "local_engine", "down", ()),
    (["local", "dbt"], "local_engine", "dbt", ([],)),
    (["release", "build", "--version", "v1"], "release", "main", ("build", "v1")),
    (["release", "fetch"], "release", "main", ("fetch", "local")),
    (["bundle", "deploy", "-t", "prod"], "bundle", "deploy", ("prod",)),
    (["bundle", "validate"], "bundle", "validate", ("dev", None)),
    (["build-changed", "--", "-x"], "build_changed", "main", (["-x"], None)),
    (["setup", "--alias", "pehe", "--yes"], "setup_dev", "main", ("pehe", True)),
])
def test_commands_are_routed(project, monkeypatch, argv, module, function, expected):
    calls = []
    monkeypatch.setattr(getattr(cli, module), function,
                        lambda proj, *args: calls.append((proj.root, args)) or 7)
    assert cli.main(argv) == 7
    assert calls == [(project.resolve(), expected)]


def test_setup_error_exits_with_message(project, monkeypatch, capsys):
    def broken(proj):
        raise devenv.SetupError("fix this first")

    monkeypatch.setattr(cli.checks, "parse", broken)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["parse"])
    assert exit_info.value.code == 1
    assert "error: fix this first" in capsys.readouterr().err


def test_project_dir_option(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["--project-dir", str(tmp_path), "parse"])
    assert "not a data product repository" in capsys.readouterr().err


def test_missing_tool_is_reported_without_traceback(project, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(project))
    with pytest.raises(SystemExit):
        cli.main(["parse"])
    assert "`dbt` is not installed or not on PATH." in capsys.readouterr().err
