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
        return yaml.safe_load(f)
