**Non-ASCII names no longer break the checks that read git.** On Windows,
PolicyForge read git's output in the system's legacy codepage instead of
UTF-8, so any name with an accent came back garbled:

- **An edited page named with an accent, such as `café.md`, was reported as
  having no uncommitted changes.** The check that stops an edit overwriting
  work you have not committed was silently off for that page.
- A reviewer named José was recorded in the crosswalk overlay as `JosÃ©`.
- A committed catalog containing non-ASCII text was compared against a
  garbled copy of itself, and one containing certain bytes crashed.
- Authors of wiki pages were shown garbled, and paths under a folder with an
  accent were printed in full instead of relative to the repository.

All of these now read UTF-8. Where the output is used as data, such as a
path, a name that gets recorded, or a catalog, text that is not valid UTF-8
now stops with an error naming the command, instead of being recorded with
the bad characters replaced. Where it is only shown to you, such as an error
message, such characters are shown as `�`.
