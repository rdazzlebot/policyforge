**With entailment switched on, an answer whose own cited passages disagree
with each other now says so, naming both.** Previously it said nothing: the
unsupported-claim check stops at the first passage that carries a sentence,
so a sentence supported by `[1]` and contradicted by `[2]` produced no
finding at all — and the absence of a finding reads as the documents
agreeing. **Expect new warnings on answers that drew one claim from two
documents**, under their own heading rather than as unsupported claims,
because the claim is carried; it is carried by a source another cited
source denies, and that is the more useful thing to be told. No extra model
calls: both findings are read off one pass of judging.
