**You can now tell `policyforge coverage` which HITRUST levels apply to
you.** Until now it counted every level in your HITRUST export, including
levels your organisation is not assessed at. Declare yours in config under
`frameworks.scoping` (see `config/config.example.yaml`):

- `maturity`: the maturity level you are assessed at. For each control
  reference, the highest statement at or below it is counted, and the report
  names any reference counted at a lower level because it has no statement
  at yours.
- `overlays`: the overlay levels that apply to you, by name. Names are
  matched against your export's own level labels, ignoring case and spacing.
  A name that matches none is refused, and the error names the closest
  labels.

The key is the framework as your catalog names it: `hitrust-csf` for a
HITRUST export. A key that matches no loaded per-level framework is refused,
and the error names the keys that are loaded, so a declaration is never
silently ignored.

If you declare nothing, every level is still counted, and the report now
says so and tells you where to declare your levels.
