**`/satisfies` no longer reports an AI topic's anchors as "cited nowhere"
when its documents cite them.** The command counted only NIST SP 800-53
citations as answering for a topic's anchors, so every AI RMF anchor was
listed as a gap, however the documents cited it. On the Standards generated
for the shipped registry's five AI topics, all 19 of their anchors were
listed; now none are. That section is the one an assessor reads first, and
it was telling you to fix documents that were already right. A citation now
counts when its framework is one a topic can anchor (SP 800-53 or the AI
RMF). A citation of the AI RMF Playbook still does not: it shares the
Core's ids, and NIST's suggestions do not answer for a Core outcome. 800-53
results are unchanged.
