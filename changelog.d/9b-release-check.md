**Nothing user-facing.** `scripts/release_check.py` is a release step for
maintainers: after cutting a tag it asserts that the published Homebrew
formula installs that tag, that its pinned resources match
`requirements/runtime.txt`, and that no changelog fragment survived the
release. It exists because 1.4.0 was declared done while `brew install` —
the first command in this project's README — still served 1.3.0 for about
three hours.
