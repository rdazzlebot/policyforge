**A drift report now shows an AI RMF subcategory change reaching the topic
that anchors its category.** `policyforge drift` decided which topics a
changed control reaches by the NIST SP 800-53 rule alone, so a change to
"Govern 1.1" reached no topic anchoring "Govern 1". It now uses the same
rule as `/coverage` for the catalogs topics anchor. A change in the NIST AI
RMF Playbook reaches no topic, since a topic never anchors the Playbook.
