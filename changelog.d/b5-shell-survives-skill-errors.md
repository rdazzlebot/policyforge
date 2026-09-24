**A command that fails in `policyforge zardoz` no longer ends the session.**
Any error a shell command raised used to exit the whole shell with a
traceback, losing the session's state, including the refusals made louder in
this release, such as `/drift` refusing output that is not UTF-8. Now an
expected refusal prints its message, an unexpected error prints its full
traceback, and both are followed by a line saying the command failed and the
session continues. A failed command never prints output that looks as though
it succeeded. Ctrl-C and Ctrl-D behave as before.
