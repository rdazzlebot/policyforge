"""Loading config.yaml, including the shapes it should refuse.

Seventeen lines and no tests, which understates what they decide. Every
command starts by calling this, so a bad return value here does not fail
here — it fails several frames deeper, inside a provider, as an
AttributeError that never mentions the config file.
"""

from __future__ import annotations

import pytest

from policyforge.config import load_config


def _config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_populated_config_loads(tmp_path):
    path = _config(tmp_path, "provider: anthropic\nmodel: claude-opus-5\n")

    assert load_config(path) == {"provider": "anthropic", "model": "claude-opus-5"}


def test_a_missing_file_says_how_to_make_one(tmp_path):
    with pytest.raises(FileNotFoundError) as caught:
        load_config(tmp_path / "nope.yaml")

    assert "config.example.yaml" in str(caught.value)


@pytest.mark.parametrize("text", ["", "   \n", "# nothing configured yet\n"])
def test_an_empty_config_is_refused_by_name(tmp_path, text):
    """`yaml.safe_load` returns None for these, which every caller then
    dereferences. The old failure was "'NoneType' object has no attribute
    'get'" from inside a provider, with no mention of the file."""
    with pytest.raises(ValueError) as caught:
        load_config(_config(tmp_path, text))

    assert "config.yaml" in str(caught.value)
    assert "empty" in str(caught.value)


@pytest.mark.parametrize("text", ["- one\n- two\n", "just a string\n", "42\n"])
def test_a_config_that_is_not_a_mapping_is_refused_by_name(tmp_path, text):
    """A top-level list is the shape a real config drifted into once
    already, for the `frameworks:` key."""
    with pytest.raises(ValueError) as caught:
        load_config(_config(tmp_path, text))

    assert "mapping" in str(caught.value)


def test_the_error_names_the_type_that_was_found(tmp_path):
    """So the reader can see what they wrote without opening the file."""
    with pytest.raises(ValueError) as caught:
        load_config(_config(tmp_path, "- one\n"))

    assert "list" in str(caught.value)
