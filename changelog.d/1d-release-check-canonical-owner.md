**The release check now refuses a Homebrew formula whose download address
names the repository's old owner.** Such a formula installs perfectly —
GitHub forwards the old address — so the check's own install test could not
see it, and it would have kept working only until anything was created at
the old name. The address is now compared as written. Release tooling only;
nothing a user installs changes.
