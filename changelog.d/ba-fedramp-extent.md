**The FedRAMP loader now refuses a parse that dropped a rule the dataset
declares.** Every `CTL` entry is either tailored or is not a mapping, and
the third outcome — silently absent — is no longer possible.

FedRAMP publishes no machine-readable baseline any more, so the
consolidated rules dataset is the whole of what this catalog can know. A
short parse produced a tailoring that was internally consistent, every
entry well-formed, and missing controls FedRAMP requires — with nothing
else to notice the shortfall against.

Nothing about a correct parse changes: the published dataset reconciles
exactly, 79 entries tailored of 79 declared.
