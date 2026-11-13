CHANGES NEEDED

medium | fieldshift/tools/fertilizer.py:220 | Overflow fix remains incomplete: tiny positive grades produce HTTP 500 or `complete` with null calculations. | Reject underflowed denominators and nonfinite results; add regression tests.

medium | fieldshift/tools/irrigation.py:370 | Two days with finite `precip_in=1e308` return `complete` with null rainfall/drainage totals. | Validate arithmetic results and return typed 400s on overflow.

medium | fieldshift/field/zones.py:178 | Unknown change-report zone IDs are silently ignored, returning `complete` without verification flags or prompts. | Reject unknown zone IDs or emit an explicit manual-check prompt.