"""yaml_edit.set_value: set a scalar by key path, keeping comments and layout."""

import pytest
import yaml

from dbtp import yaml_edit
from dbtp.devenv import SetupError

TEXT = '''# top comment
variables:
  catalog:
    description: x  # keep me
  schedule:
    default: "0 0 5 * * ?"

targets:
  dev:
    variables:
      catalog: <dev>
  prod:
    variables:

      # a comment inside
      catalog: <prod>   # trailing
    list:
      - catalog: not this one
'''


def test_sets_the_value_at_the_path_only():
    out = yaml_edit.set_value(TEXT, ("targets", "prod", "variables", "catalog"), "prod_cat")
    assert "      catalog: prod_cat   # trailing\n" in out
    assert "catalog: <dev>" in out
    assert out.replace("prod_cat", "<prod>") == TEXT


def test_quoted_values_stay_quoted_and_unsafe_values_get_quoted():
    out = yaml_edit.set_value(TEXT, ("variables", "schedule", "default"), "0 30 6 * * ?")
    assert '    default: "0 30 6 * * ?"\n' in out
    out = yaml_edit.set_value(TEXT, ("targets", "dev", "variables", "catalog"), "a: b # c")
    assert yaml.safe_load(out)["targets"]["dev"]["variables"]["catalog"] == "a: b # c"


@pytest.mark.parametrize("path", [("targets", "qa", "variables", "catalog"),
                                  ("targets", "dev", "variables")])
def test_missing_key_or_mapping_is_an_error(path):
    with pytest.raises(SetupError):
        yaml_edit.set_value(TEXT, path, "x")
