**The call ledger now records what a failed re-send cost.** When a reasoning
model came back empty, was re-sent with more room and came back empty again,
the ledger row had no cost and no request id, so the re-send's charge was
recorded nowhere. The row now carries the cost of both attempts and the
re-send's request id. A cascade that falls back to its stronger model
likewise counts the first model's billed attempts in the row, and now says
so before it re-sends, as a re-send to the same model already did.
