"""Explicit mapping from catalog ``region`` text to North Carolina region tags.

Guidance only applies to a field when the rule's ``region`` text maps to the field's region. The
mapping is an explicit table: a ``region`` string that is not in the table is ``unknown``, never
guessed. The tags are deliberately coarse (the catalog does not support finer matching):

* ``mountains``, ``piedmont``, ``coastal_plain`` and ``tidewater`` are mutually exclusive tags for
  where a field sits. Tidewater is the eastern edge of the Coastal Plain; a field there is tagged
  ``tidewater`` (and matches rules written for the Coastal Plain).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

NC_REGION_TAGS = ("mountains", "piedmont", "coastal_plain", "tidewater", "northeast")

# Which tags a plan region also satisfies (tidewater is part of the Coastal Plain).
_IMPLIES = {
    "northeast": {"northeast", "tidewater", "coastal_plain"},
    "tidewater": {"tidewater", "coastal_plain"},
}

RegionMatch = Literal["match", "no_match", "unknown"]


@dataclass(frozen=True)
class RegionRule:
    """How one catalog ``region`` string maps onto field region tags."""

    scope: Literal["nc_all", "nc_tags", "outside_nc", "us_general"]
    tags: frozenset[str] = frozenset()  # for nc_tags
    exclude: frozenset[str] = frozenset()  # for nc_all
    # Field tags too coarse to decide: a "coastal_plain" field may or may not be in the sub-region
    # the rule is written for, so the answer is ``unknown`` rather than a guess.
    ambiguous: frozenset[str] = frozenset()
    note: str = ""


def _tags(*t: str) -> frozenset[str]:
    return frozenset(t)


_NC_ALL = RegionRule("nc_all")

# Every distinct ``region`` string in the v1/v2 crop_rules.csv.
REGION_MAP: dict[str, RegionRule] = {
    "North Carolina statewide": _NC_ALL,
    "North Carolina": _NC_ALL,
    "North Carolina (Arkansas data)": RegionRule(
        "nc_all", note="NC guide table that cites Arkansas data; applies statewide"
    ),
    "North Carolina (11-location trials)": _NC_ALL,
    "Southeastern US (NC study)": _NC_ALL,
    "NC Piedmont": RegionRule("nc_tags", _tags("piedmont")),
    "NC Piedmont (Cleveland County)": RegionRule("nc_tags", _tags("piedmont")),
    "NC Piedmont and mountains": RegionRule("nc_tags", _tags("piedmont", "mountains")),
    "NC Piedmont and western NC": RegionRule("nc_tags", _tags("piedmont", "mountains")),
    "NC Coastal Plain": RegionRule("nc_tags", _tags("coastal_plain", "tidewater")),
    # Northeastern NC is the eastern edge of the Coastal Plain: only a "tidewater" field matches.
    # Only a field known to be in northeastern NC (for example Hertford County) matches; a generic
    # Coastal Plain or Tidewater field may or may not be there, so it is ``unknown``.
    "Hertford County NC (northeastern)": RegionRule(
        "nc_tags", _tags("northeast"), ambiguous=_tags("coastal_plain", "tidewater")
    ),
    "Northeastern NC (Hertford County article)": RegionRule(
        "nc_tags", _tags("northeast"), ambiguous=_tags("coastal_plain", "tidewater")
    ),
    "NC outside Tidewater": RegionRule(
        "nc_all", exclude=_tags("tidewater"), ambiguous=_tags("coastal_plain")
    ),
    "NC excluding Tidewater": RegionRule(
        "nc_all", exclude=_tags("tidewater"), ambiguous=_tags("coastal_plain")
    ),
    # Broad multi-state regions that include North Carolina.
    "General US": RegionRule("us_general"),
    "Southern US": RegionRule("us_general"),
    "Eastern US crimson clover zone": RegionRule("us_general"),
    # Other places: kept as sourced context, never applied to an NC field automatically.
    "Pennsylvania": RegionRule("outside_nc"),
    "Virginia Piedmont": RegionRule("outside_nc"),
    "Indiana (Purdue Extension reference)": RegionRule("outside_nc"),
    "Alabama research": RegionRule("outside_nc"),
}


OTHER_STATES = frozenset(
    """alabama alaska arizona arkansas california colorado connecticut delaware florida georgia
    hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts
    michigan minnesota mississippi missouri montana nebraska nevada ohio oklahoma oregon
    pennsylvania tennessee texas utah vermont virginia washington wisconsin wyoming""".split()
) | {"new hampshire", "new jersey", "new mexico", "new york", "north dakota", "rhode island",
     "south carolina", "south dakota", "west virginia"}  # fmt: skip
_NC_MARKER_RE = re.compile(r"\bnc\b|north carolina")


# Two-letter codes of other states. Upper case always counts ("VA Piedmont"); lower case counts only
# for codes that are not ordinary words ("in", "or", "me" are not treated as states).
_OTHER_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
_UNAMBIGUOUS_LOWER = frozenset({"va", "sc", "ga", "tn", "wv", "md", "fl", "ky", "pa"})


def _mentions_other_state(t: str, original: str | None = None) -> bool:
    if _NC_MARKER_RE.search(t):  # "Washington County, NC" is North Carolina
        return False
    for tok in re.split(r"[^A-Za-z]+", original if original is not None else t):
        if (tok in _OTHER_CODES) or (tok in _UNAMBIGUOUS_LOWER):
            return True
    words = set(re.split(r"[^a-z]+", t))
    if any(state in words for state in OTHER_STATES if " " not in state):
        return True
    return any(state in t for state in OTHER_STATES if " " in state)


def region_scope(text: str | None) -> Literal["unspecified", "nc", "outside", "unrecognized"]:
    """Is a free-text field region in NC? Another state's name anywhere means ``outside``."""
    if not text or not text.strip():
        return "unspecified"
    t = text.strip().lower().replace("_", " ")
    if _mentions_other_state(t, text):
        return "outside"
    if normalize_field_region(t) is not None or _NC_MARKER_RE.search(t):
        return "nc"
    return "unrecognized"


def normalize_field_region(text: str | None) -> str | None:
    """Turn a free-text field region ("NC Piedmont", "Union County") into a region tag, or ``None``.

    Text that names another state ("Virginia Piedmont") never maps to an NC tag.
    """
    if not text:
        return None
    t = text.strip().lower().replace("_", " ")
    if _mentions_other_state(t, text):
        return None
    if "hertford" in t or "northeast" in t:
        return "northeast"
    if "tidewater" in t:
        return "tidewater"
    if "coastal" in t:
        return "coastal_plain"
    if "piedmont" in t or t.startswith("union county"):
        return "piedmont"
    if "mountain" in t or "western nc" in t:
        return "mountains"
    return None


def region_match(rule_region: str | None, field_region: str | None) -> tuple[RegionMatch, str]:
    """Does a rule written for ``rule_region`` apply to a field in ``field_region``?

    ``field_region`` is a free-text region or tag. Returns ``(match, reason)``.
    """
    if not rule_region:
        return "unknown", "rule has no region text"
    rule = REGION_MAP.get(rule_region)
    if rule is None:
        return "unknown", f"rule region '{rule_region}' is not in the region mapping table"
    if rule.scope == "outside_nc":
        return "no_match", f"rule region '{rule_region}' is outside North Carolina"
    if rule.scope == "us_general":
        return "match", f"rule region '{rule_region}' covers North Carolina"
    tag = normalize_field_region(field_region)
    if rule.scope == "nc_all":
        if tag is None:
            if rule.exclude:
                return (
                    "unknown",
                    f"rule region '{rule_region}' excludes {sorted(rule.exclude)} "
                    "and the field region is not known",
                )
            return "match", f"rule region '{rule_region}' covers all of North Carolina"
        if tag in rule.ambiguous:
            return "unknown", (
                f"rule region '{rule_region}' excludes {sorted(rule.exclude)}; a {tag} field "
                "may or may not be there, so the sub-region is needed"
            )
        if _IMPLIES.get(tag, {tag}) & rule.exclude:
            return "no_match", f"rule region '{rule_region}' excludes the field's region ({tag})"
        return "match", f"rule region '{rule_region}' covers the field's region ({tag})"
    # nc_tags
    if tag is None:
        return "unknown", (
            f"rule region '{rule_region}' is specific to {sorted(rule.tags)}; "
            "the field region is not known"
        )
    if tag in rule.ambiguous:
        return "unknown", (
            f"rule region '{rule_region}' is specific to {sorted(rule.tags)}; a {tag} field "
            "may or may not be there, so the sub-region is needed"
        )
    if _IMPLIES.get(tag, {tag}) & rule.tags:
        return "match", f"rule region '{rule_region}' covers the field's region ({tag})"
    return "no_match", f"rule region '{rule_region}' does not cover the field's region ({tag})"
