**`scripts/release_check.py` now installs from `rdazzleman/tap`**, the tap's
new home after the repository and tap moved from `rdazzlebot`. Release
tooling only; nothing a user installs changes.

The check exists to prove that the install command a new user types
actually works, so it has to name the command the README names. Pointed at
the old owner, it would have gone on passing while testing a path the README
no longer documents.
