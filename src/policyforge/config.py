from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config/config.yaml")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config/config.example.yaml to "
            f"{path} and fill in your model/provider choices."
        )
    with path.open() as f:
        loaded = yaml.safe_load(f)

    # An empty or comment-only file parses to None, and a stray top-level
    # list parses to a list. Both then travel as far as the first
    # `config.get(...)` and fail as "'NoneType' object has no attribute
    # 'get'" — an error that never mentions the config file, from a
    # traceback deep inside a provider. Say it here, where the file is
    # still in hand.
    if loaded is None:
        raise ValueError(
            f"{path} is empty. Copy config/config.example.yaml over it and "
            f"fill in your model/provider choices."
        )
    if not isinstance(loaded, dict):
        raise ValueError(
            f"{path} should contain a mapping of settings, but its top level "
            f"is {type(loaded).__name__}. Compare it with "
            f"config/config.example.yaml."
        )
    return loaded
