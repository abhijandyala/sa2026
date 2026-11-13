CHANGES NEEDED

high | fieldshift/api/routes.py:139 | Arbitrary coordinates, including (0,0), receive unchanged Union County weather results while echoing the requested location. | Resolve the weather context for the point or reject unsupported locations.

medium | fieldshift/api/routes.py:198 | Replay accepts an unknown crop and returns ordinary weather rows with no checks; comparison correctly marks the same plan unsupported. | Apply consistent support validation and expose the unsupported status.

medium | fieldshift/compare/sensitivity.py:112 | Zero evaluable seasons incorrectly means inapplicable: clover’s applicable cc_soil_02 manual check returns status=inapplicable. | Preserve manual_check/unknown statuses; require actual applicability results before declaring inapplicable.

medium | fieldshift/api/routes.py:110 | Comparing add_grain_crop labels its second leg rotation_id=current_practice, misidentifying preset membership. | Derive membership from the requested rotations and support plans shared by multiple presets.
## Agent A responses (2026-11-13)
All four fixed with tests (no r3 per the two-round limit): a requested point outside the committed Union County cell (or outside NC) returns every plan `unsupported: unsupported_location` plus the location block, never Union weather; replay and sensitivity return the same `unsupported` status as compare for unknown crops; sensitivity preserves `manual_check`/`unknown`/`inapplicable` from the rule results; rotation membership (`rotation_ids`) comes from the requested rotations, and a plan shared by presets lists each.
