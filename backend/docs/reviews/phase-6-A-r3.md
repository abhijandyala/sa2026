CHANGES NEEDED

medium | fieldshift/api/routes.py:194 | Maturity group is omitted from hashing: null, 0, 3, and 5 produce identical input_hash, result_id, and plan_version despite different checks. | Include maturity_group in the canonical input.

medium | fieldshift/api/routes.py:63 | Empty and whitespace maturity groups return 400 instead of unknown. | Normalize blank strings to None before strict validation; preserve 0.

medium | docs/api/openapi.json:189 | Bounds use unrecognized JSON Schema keywords ge/le; schema validation accepts -1 and 11. | Apply bounds to each numeric type and regenerate minimum/maximum.

low | docs/api/presets.md:19 | Preset documentation still says wheat is unavailable and lists TBD dates. | Document v2 partial, the v1 fallback, and assumed demo dates; update examples/README.md too.