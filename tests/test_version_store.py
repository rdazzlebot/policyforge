"""history/version_store.py tests: recording, no-op dedup on identical
content, diffing, and reading history back."""

from __future__ import annotations


def test_record_version_creates_first_version(tmp_path):
    from policyforge.history.version_store import load_history, record_version

    record = record_version(
        tmp_path, "standard/auth-mgmt", "# Title\n\nBody.\n", source="generate", metadata={"org": "Acme"}
    )

    assert record is not None
    assert record.version == 1
    assert record.source == "generate"
    assert record.lines_added > 0
    assert record.lines_removed == 0
    assert record.metadata == {"org": "Acme"}

    history = load_history(tmp_path, "standard/auth-mgmt")
    assert len(history) == 1
    assert history[0] == record


def test_record_version_skips_identical_content(tmp_path):
    from policyforge.history.version_store import load_history, record_version

    record_version(tmp_path, "standard/auth-mgmt", "# Title\n\nBody.\n", source="generate")
    second = record_version(tmp_path, "standard/auth-mgmt", "# Title\n\nBody.\n", source="generate")

    assert second is None
    assert len(load_history(tmp_path, "standard/auth-mgmt")) == 1


def test_record_version_bumps_version_and_computes_diff_stats_on_change(tmp_path):
    from policyforge.history.version_store import load_history, record_version

    record_version(tmp_path, "standard/auth-mgmt", "# Title\n\nOld body.\n", source="generate")
    second = record_version(
        tmp_path, "standard/auth-mgmt", "# Title\n\nNew body.\nExtra line.\n", source="generate"
    )

    assert second.version == 2
    assert second.lines_added == 2
    assert second.lines_removed == 1
    assert len(load_history(tmp_path, "standard/auth-mgmt")) == 2


def test_diff_versions_returns_unified_diff(tmp_path):
    from policyforge.history.version_store import diff_versions, record_version

    record_version(tmp_path, "standard/auth-mgmt", "line one\n", source="generate")
    record_version(tmp_path, "standard/auth-mgmt", "line one\nline two\n", source="generate")

    diff = diff_versions(tmp_path, "standard/auth-mgmt", 1, 2)

    assert "+line two" in diff
    assert "v1" in diff and "v2" in diff


def test_load_history_empty_when_nothing_recorded(tmp_path):
    from policyforge.history.version_store import load_history

    assert load_history(tmp_path, "standard/never-generated") == []


def test_record_version_tracks_multiple_slugs_independently(tmp_path):
    from policyforge.history.version_store import load_history, record_version

    record_version(tmp_path, "standard/auth-mgmt", "standard content\n", source="generate")
    record_version(tmp_path, "policy/auth-mgmt", "policy content\n", source="generate")

    assert len(load_history(tmp_path, "standard/auth-mgmt")) == 1
    assert len(load_history(tmp_path, "policy/auth-mgmt")) == 1
