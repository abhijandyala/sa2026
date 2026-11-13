CHANGES NEEDED

medium | fieldshift/metrics/rules.py:361 | `organic_grain` is unmapped; v2 organic wheat rules return `unknown` for conventional plans instead of `inapplicable`. | Map the composite requirement to organic/grain tags; test conventional and organic plans.

medium | fieldshift/metrics/rules.py:604 | Both June and July maturity-group rules evaluate regardless of planting date; June MG4 incorrectly fails the July rule. | Honor each row’s planting-date context, or return `manual_check` when applicability is unresolved.