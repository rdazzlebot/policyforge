**Fixed: every AI topic retrieved zero controls.** `build_synthesis_topic`
resolved a topic's anchors against one hardcoded framework key, so a topic
anchoring `Govern 1` found nothing — while `/coverage` reported those same
topics owning 91 requirements.

**Two views of one registry, disagreeing, and the optimistic one was the
user-facing one.** Coverage said 905 owned and 82%; synthesis retrieved
nothing for the requirements that figure was made of.

The anchor lookup now asks `TOPIC_ANCHORS`, as the rest of the codebase
already does. 800-53 topics are unchanged and still expand through the
crosswalk; a topic anchoring both catalogs now yields obligations grounded
in 800-53 alongside outcomes cited from the AI RMF.
