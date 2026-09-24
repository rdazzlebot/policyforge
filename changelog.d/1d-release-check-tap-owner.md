**`scripts/release_check.py` now installs from `rdazzleman/tap`**, the tap's
new home after the repository and tap moved from `rdazzlebot`. Release
tooling only; nothing a user installs changes.

The check exists to prove that the install command a new user types
actually works, so it has to name the command the README names. Pointed at
the old owner, it would have gone on passing while testing a path the README
no longer documents.

**And the install check could not complete on Windows at all.** It read
Homebrew's output with the system's default encoding — cp1252 on the
machine the release is cut from — and crashed on the first non-ASCII byte
Homebrew prints, before it could say whether the install worked. It now reads output as UTF-8, and prints it without crashing on a
character the console cannot show. The crash only ever blocked a release rather than
passing one falsely, but it blocked it for a reason unrelated to the
install, and the obvious response to a traceback at the cut is to skip the
check.
