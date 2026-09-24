**`import-confluence` no longer crashes when a page has changed.** When the
imported page differed from the last recorded version of the document, the
command wrote the file and the history entry, then exited 1 with a
`TypeError` instead of printing the `policyforge history` command that shows
what changed. It now exits 0 and prints that command. The printed command
runs as shown.
