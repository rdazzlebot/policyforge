**Documentation links and the container image's source label now point at the
repository's new home, `rdazzleman/policyforge`.** The
project moved from `rdazzlebot`; the old addresses still work only because
GitHub forwards them, and that forwarding stops if anything is ever created at
the old name. Updated: the security-advisory link in `SECURITY.md`, the `pipx`
install commands in the README, the formula URL template in `CONTRIBUTING.md`,
a CI run link in the security architecture notes, and the
`org.opencontainers.image.source` label every built image carries.

**Homebrew install commands are unchanged for now.** `brew install rdazzlebot/tap/policyforge` still works and still points at the right place;
it changes only once the tap itself has moved.

**Removed `prev.md` from the repository root** — a copy of the 1.5.0 changelog
left in the 1.6.0 release by mistake. It was never used by anything and
duplicated release history for anyone searching it.
