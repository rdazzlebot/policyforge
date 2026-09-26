""".github/dependabot.yml: one pip entry per directory, grouped per dependency (#414).

Two pip entries reached the same locks, so every bump arrived as two pull
requests. GitHub forbids overlapping directories across blocks of one
ecosystem. These pin the shape that fixes it; whether Dependabot then opens
one pull request per bump can only be seen on a live run.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / ".github" / "dependabot.yml"


def _updates() -> list[dict]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["updates"]


def _dirs(update: dict) -> list[str]:
    return [update["directory"]] if "directory" in update else list(update["directories"])


def test_no_directory_appears_in_two_blocks_of_one_ecosystem():
    """GitHub's literal rule: one directory, one block per ecosystem.

    **This does NOT catch #414's shape**, and says so: "/" and
    "/requirements" are different strings, yet "/" also reached the locks
    under requirements/. Splitting the pip entry back into those two blocks
    passes this test (measured on #414); the test below is the #414 guard.
    """
    seen: dict[tuple[str, str], int] = {}
    for index, update in enumerate(_updates()):
        for directory in _dirs(update):
            key = (update["package-ecosystem"], directory.rstrip("/") or "/")
            assert key not in seen, (
                f"{key} is in update blocks {seen[key]} and {index}: GitHub forbids "
                "one directory in two blocks of one ecosystem"
            )
            seen[key] = index


def test_the_lock_directories_are_one_block_grouped_per_dependency():
    """Both "/" (pyproject) and "/requirements" (the two locks) reach the same
    files, so they are one block, and `group-by: dependency-name` makes one
    pull request per bump across them."""
    blocks = [u for u in _updates() if u["package-ecosystem"] == "pip" and "/" in _dirs(u)]
    assert len(blocks) == 1, blocks
    (block,) = blocks
    assert set(_dirs(block)) == {"/", "/requirements"}
    grouped = [
        g for g in (block.get("groups") or {}).values() if g.get("group-by") == "dependency-name"
    ]
    assert grouped, "no group sets group-by: dependency-name"
    # The group must cover EVERY dependency (policyforge-9b on #454): narrowed
    # to `["pydantic*"]`, every other bump went back to one pull request per
    # directory -- #414's defect -- and the assert above still passed. So:
    # all names, and nothing that filters them back out.
    assert any(
        g.get("patterns") == ["*"]
        and not g.get("exclude-patterns")
        and not g.get("dependency-type")
        and not g.get("update-types")
        for g in grouped
    ), f"the dependency-name group does not cover every dependency: {grouped}"
