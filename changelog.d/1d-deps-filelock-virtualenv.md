**CI's lock moves `filelock` to 3.32.7 and `virtualenv` to 21.7.10**, the
versions Dependabot proposed in #239–#242, regenerated with the lock's own
header command rather than merged as Dependabot wrote them. Both are
dev-only tools; nothing a user installs changes.

**The documented way to do that has a hazard, now written beside the rule.**
The lock header's command alone moves nothing, and the obvious addition —
`--upgrade-package <name>` — upgrades to the *latest* release, which ignores
the seven-day cooldown the Dependabot config exists to enforce. On the day
this was done that reached for `filelock` 4.0.3, a major version, and
`virtualenv` 21.11.1 — both uploaded that same day. Naming the proposed
version (`--upgrade-package "filelock==3.32.7"`) reproduced Dependabot's edit
byte-for-byte.
