import pytest

from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.field.regions import REGION_MAP, normalize_field_region, region_match


@pytest.mark.parametrize("catalog_dir", ["v1", "v2"])
def test_every_catalog_region_text_is_in_the_mapping_table(catalog_dir):
    from fieldshift.catalogs import CATALOGS_ROOT

    regions = set(CatalogIndex(load_catalog(CATALOGS_ROOT / catalog_dir)).regions())
    assert regions - set(REGION_MAP) == set()


@pytest.mark.parametrize(
    ("text", "tag"),
    [("NC Piedmont", "piedmont"), ("Union County", "piedmont"), ("Coastal Plain", "coastal_plain"), ("Hertford County", "northeast"),
     ("Virginia Piedmont", None), ("Pennsylvania mountains", None), ("Washington County, NC", None),
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
        ("NC Coastal Plain", "northeast", "match"),
        ("Hertford County NC (northeastern)", "northeast", "match"),
        ("Hertford County NC (northeastern)", "tidewater", "unknown"),
        ("Hertford County NC (northeastern)", "coastal_plain", "unknown"),
        ("Hertford County NC (northeastern)", "piedmont", "no_match"),
        ("NC outside Tidewater", "northeast", "no_match"),
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


@pytest.mark.parametrize(
    ("text", "scope"),
    [(None, "unspecified"), ("", "unspecified"), ("NC Piedmont", "nc"), ("North Carolina", "nc"),
     ("Washington County, NC", "nc"), ("Virginia Piedmont", "outside"), ("West Virginia", "outside"),
     ("South Carolina coastal", "outside"), ("Pennsylvania mountains", "outside"), ("VA Piedmont", "outside"),
     ("SC Coastal Plain", "outside"), ("va piedmont", "outside"), ("NC Piedmont", "nc"), ("in the Piedmont", "nc"),
     ("the moon", "unrecognized")],
)  # fmt: skip
def test_region_scope(text, scope):
    from fieldshift.field.regions import region_scope

    assert region_scope(text) == scope
