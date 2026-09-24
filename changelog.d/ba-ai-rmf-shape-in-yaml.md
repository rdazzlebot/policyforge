**The AI RMF catalog's expected shape now lives in its `framework.yaml`**
(`shape:`, 19 categories and 72 subcategories), next to the revision's other
pins, instead of in the loader. `policyforge etl-ai-rmf` reads it from the
catalog it regenerates and refuses any page that parses to a different
shape. A refusal is now a one-line error instead of a traceback. The command
never rewrites the pin, so moving to a new revision is a deliberate edit.
