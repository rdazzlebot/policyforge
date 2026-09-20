**Nothing user-facing.** `scripts/release_check.py` gains assertion 1b:
the published formula's `sha256` must match the archive its `url` actually
serves. Naming the right tag beside a stale hash makes every `brew install` fail at verification, and assertion 1 reported that formula as
correct.
