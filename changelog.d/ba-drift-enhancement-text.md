**`policyforge drift` now reports a reworded enhancement.** Before, drift
compared a control's own text and its list of enhancement ids, so a change
to the text of an enhancement, such as NIST SP 800-53's AC-2(3), an AI RMF
subcategory or a HIPAA implementation specification, was never reported.
Such a change is now reported under the enhancement's own id, and reaches
the topics and documents that id reaches. The first scheduled drift run
after this change may go red on upstream edits that were always there and
never reported; that is the job working.
