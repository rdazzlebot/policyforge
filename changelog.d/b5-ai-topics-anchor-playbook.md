**A Standard for an AI topic now says what NIST suggests for each AI RMF
subcategory the topic covers.** `generate --tier standard` gives it the NIST AI
RMF Playbook's actions for exactly those subcategories. The Standard writes one
sentence per subcategory in NIST's voice ("NIST suggests, among its N actions
for Govern 1.4, ..."), cited to the actions it draws on. Policies and
Procedures are not given them, and the Playbook is still not something a topic
owns, so `/coverage` is unchanged.

**If a Standard's Playbook sentences would fail `policyforge check`,
generation now fixes them or refuses.** A sentence the check rejects, or a
subcategory with no sentence, is regenerated up to three times. If one still
fails, `generate` stops with an error naming the subcategory and writes no
file, instead of writing a Standard that `check` would reject.
