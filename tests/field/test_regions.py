import pytest

from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.field.regions import REGION_MAP, normalize_field_region, region_match


def test_every_v1_region_text_is_in_the_mapping_table():
    regions = set(CatalogIndex(load_catalog()).regions())
    assert regions - set(REGION_MAP) == set()


@pytest.mark.parametrize(
    ("text", "tag"),
    [("NC Piedmont", "piedmont"), ("Union County", "piedmont"), ("Coastal Plain", "coastal_plain"),
     ("Tidewater NC", "tidewater"), ("western NC", "mountains"), ("North Carolina", None), (None, None)],
)  # fmt: skip
def test_normalize_field_region(text, tag):
    assert normalize_field_region(text) == tag


@pytest.mark.parametrize(
    ("rule_region", "field", "expected"),
    [
        ("NC Piedmont", "piedmont", "match"),
        ("NC Piedmont", "coastal_plain", "no_match"),
        ("NC Piedmont and mountains", "mountains", "match"),
        ("NC Coastal Plain", "tidewater", "match"),
        ("NC outside Tidewater", "tidewater", "no_match"),
        ("NC outside Tidewater", "piedmont", "match"),
        ("NC outside Tidewater", None, "unknown"),
        ("North Carolina statewide", None, "match"),
        ("General US", "piedmont", "match"),
        ("Pennsylvania", "piedmont", "no_match"),
        ("NC Piedmont", None, "unknown"),
        ("Mars", "piedmont", "unknown"),  # unmapped region is unknown, never guessed
        (None, "piedmont", "unknown"),
    ],
)
def test_region_match(rule_region, field, expected):
    assert region_match(rule_region, field)[0] == expected
