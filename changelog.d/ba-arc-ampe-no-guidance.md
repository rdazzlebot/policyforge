**Nineteen ARC-AMPE fields stop saying "there is no guidance" as though it
were guidance.** Nine control discussions and ten enhancement
requirements shipped a sentence whose entire content is CMS's template
boilerplate — *"There are no supplemental control requirements & guidance
at this time."* — and it rendered into generated documents as if CMS had
written it as supplemental guidance.

**If you have generated a policy or an SSP that cites one of these, the
text was template furniture, not a requirement.** Affected: `AT-4`,
`AU-7`, `AU-8`, `IA-6`, `IR-5`, `PE-2`, `PM-2`, `PM-3`, `PM-26`, and the
enhancements `AC-18(3)`, `AC-20(1)`, `AU-7(1)`, `IA-5(6)`, `IA-5(7)`,
`MA-3(1)`, `PL-4(1)`, `SA-11(2)`, `SA-11(8)`, `SC-8(2)`. Those fields are
now empty, which is what they always meant.

**No control was added, removed or renumbered.** 215 controls and 187
enhancements before and after — 402 baseline items, still CMS's published
figure. Only the nineteen fields changed.

**Why they were missed.** The loader already dropped this sentence, but it
looked for the literal word "and" between "requirements" and "guidance".
Eighteen of the nineteen write "**&**", and `PE-2` reads
"require**and**ents" — a find-and-replace of "&" that ran through the
middle of the word. The detection was written against the spelling in
front of whoever wrote it.

**The same check was wrong in the other direction too, and that is the
half worth knowing about.** It searched the whole cell, so a row whose
guidance genuinely discussed supplemental control requirements would have
been discarded entirely — every word of it — because the sentinel
appeared somewhere inside. No shipped row hits that today; it was waiting
for one.

The rule is now that **every sentence** in the cell must be the
boilerplate, so one real sentence beside it keeps the whole cell, and the
trailing clause is free to move between "at this time" and "for this
control" without anyone maintaining a list of endings.

No command, option or exit code changes.
