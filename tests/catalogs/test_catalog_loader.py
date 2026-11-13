from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.catalogs.validate import (
    CROPS_FILE,
    FERTILIZERS_FILE,
    RULES_FILE,
    parse_mm_dd,
)


def keys(catalog, severity="error"):
    return {(i.file, i.row, i.field) for i in catalog.issues if i.severity == severity}


# ------------------------------------------------------------------ real v1 catalogs


def test_v1_loads_with_only_the_two_blank_verified_date_warnings():
    cat = load_catalog()
    assert cat.errors == []
    assert len(cat.crops) == 5
    assert len(cat.rules) == 85
    assert len(cat.fertilizers) == 5
    assert {(i.file, i.field, i.severity) for i in cat.issues} == {
        (RULES_FILE, "verified_date", "warning")
    }
    assert sorted(cat.rule_ids_with_warning("verified_blank")) == ["fc_nut_01", "sb_nut_01"]


def test_v1_blank_verified_rows_are_kept_as_data_without_auto_n_rate():
    cat = load_catalog()
    idx = CatalogIndex(cat)
    for rid in ("fc_nut_01", "sb_nut_01"):
        r = idx.rule(rid)
        assert r is not None
        assert r.verified_date is None
        assert r.value_min is None and r.value_max is None and r.operator is None


def test_exposure_duration_several_is_kept_qualitative():
    r = CatalogIndex(load_catalog()).rule("sb_wt_02")
    assert r.exposure_duration is None
    assert r.exposure_duration_text == "several"
    assert r.exposure_unit == "days"


def test_blank_is_none_and_real_zero_stays_zero():
    cat = load_catalog()
    urea = next(f for f in cat.fertilizers if f.fertilizer_id == "urea_46_0_0")
    assert urea.p2o5_pct == 0 and urea.p2o5_pct is not None
    fc_pw_01 = CatalogIndex(cat).rule("fc_pw_01")
    assert fc_pw_01.value_max is None  # blank, not 0
    assert fc_pw_01.window_start_mm_dd is None


def test_manifest_has_hashes_and_row_counts():
    m = load_catalog().manifest
    assert m.version == "v1"
    assert m.files[RULES_FILE].rows == 85 and m.files[RULES_FILE].usable_rows == 85
    assert m.files[RULES_FILE].warnings == 2
    assert len(m.files[RULES_FILE].sha256) == 64
    assert load_catalog().manifest.content_hash == m.content_hash  # deterministic


def test_parse_mm_dd():
    assert parse_mm_dd("02-29") == (2, 29)
    assert parse_mm_dd("13-01") is None
    assert parse_mm_dd("4-20") is None
    assert parse_mm_dd("02-30") is None


# ------------------------------------------------------------------ synthetic bad-row fixtures


def test_base_fixture_is_clean(base_dir):
    cat = load_catalog(base_dir)
    assert cat.issues == []
    assert [r.rule_id for r in cat.rules] == ["fx_01", "fx_02", "fx_03", "fx_04"]


def test_bad_operator_reports_exact_row_and_field(mutate):
    cat = load_catalog(mutate(RULES_FILE, 3, "operator", "approx"))
    assert (RULES_FILE, 3, "operator") in keys(cat)
    assert "fx_02" not in {r.rule_id for r in cat.rules}
    assert {"fx_01", "fx_03", "fx_04"} <= {r.rule_id for r in cat.rules}  # other rows survive


def test_dangling_crop_refs(mutate):
    d = mutate(RULES_FILE, 2, "crop_id", "crop_zzz")
    d = mutate(RULES_FILE, 4, "previous_crop_id", "ghost_prev")
    d = mutate(RULES_FILE, 4, "next_crop_id", "ghost_next")
    cat = load_catalog(d)
    assert {
        (RULES_FILE, 2, "crop_id"),
        (RULES_FILE, 4, "previous_crop_id"),
        (RULES_FILE, 4, "next_crop_id"),
    } <= keys(cat)


def test_reversed_between(mutate):
    d = mutate(RULES_FILE, 4, "value_min", "20")
    cat = load_catalog(d)
    assert (RULES_FILE, 4, "value_max") in keys(cat)
    assert "fx_03" not in {r.rule_id for r in cat.rules}


def test_between_missing_bound(mutate):
    cat = load_catalog(mutate(RULES_FILE, 4, "value_max", ""))
    assert (RULES_FILE, 4, "value_max") in keys(cat)


def test_single_bound_operator_with_value_max(mutate):
    cat = load_catalog(mutate(RULES_FILE, 3, "value_max", "60"))
    assert (RULES_FILE, 3, "value_max") in keys(cat)


def test_duplicate_id_flags_the_later_row(mutate):
    d = mutate(CROPS_FILE, 0, "crop_id", "crop_a", copy_row_from=3)
    cat = load_catalog(d)
    errs = [i for i in cat.errors if i.code == "id_duplicate"]
    assert [(i.file, i.row, i.field) for i in errs] == [(CROPS_FILE, 4, "crop_id")]
    assert "first seen on row 2" in errs[0].message
    assert len(cat.crops) == 2  # the first occurrences stay usable


def test_non_snake_case_id(mutate):
    cat = load_catalog(mutate(CROPS_FILE, 2, "crop_id", "Crop-A"))
    assert (CROPS_FILE, 2, "crop_id") in keys(cat)


def test_fertilizer_grade_mismatch(mutate):
    cat = load_catalog(mutate(FERTILIZERS_FILE, 2, "n_pct", "45"))
    assert (FERTILIZERS_FILE, 2, "grade") in keys(cat)
    assert [f.fertilizer_id for f in cat.fertilizers] == ["fx_mes"]


def test_fertilizer_grade_ignores_trailing_s_zn_and_range(mutate):
    assert load_catalog(mutate(FERTILIZERS_FILE, 3, "grade", "12-40-0-10S-1Zn")).errors == []
    cat = load_catalog(mutate(FERTILIZERS_FILE, 3, "p2o5_pct", "140"))
    assert (FERTILIZERS_FILE, 3, "p2o5_pct") in keys(cat)


def test_bad_dates(mutate):
    d = mutate(RULES_FILE, 2, "window_start_mm_dd", "13-40")
    d = mutate(RULES_FILE, 3, "verified_date", "01/02/2026")
    cat = load_catalog(d)
    assert (RULES_FILE, 2, "window_start_mm_dd") in keys(cat)
    assert (RULES_FILE, 3, "verified_date") in keys(cat)


def test_unknown_unit_and_missing_source(mutate):
    d = mutate(RULES_FILE, 3, "unit", "furlongs")
    d = mutate(RULES_FILE, 2, "source_url", "")
    d = mutate(RULES_FILE, 4, "source_locator", "")
    cat = load_catalog(d)
    assert {
        (RULES_FILE, 3, "unit"),
        (RULES_FILE, 2, "source_url"),
        (RULES_FILE, 4, "source_locator"),
    } <= keys(cat)


def test_unknown_rule_type_and_suitability(mutate):
    d = mutate(RULES_FILE, 2, "rule_type", "vibes")
    d = mutate(RULES_FILE, 3, "suitability", "great")
    cat = load_catalog(d)
    assert {(RULES_FILE, 2, "rule_type"), (RULES_FILE, 3, "suitability")} <= keys(cat)


def test_blank_verified_date_is_a_warning_not_an_error(mutate):
    cat = load_catalog(mutate(CROPS_FILE, 2, "verified_date", ""))
    assert cat.errors == []
    assert (CROPS_FILE, 2, "verified_date") in keys(cat, "warning")
    assert len(cat.crops) == 2


def test_non_numeric_value_is_an_error_not_zero(mutate):
    cat = load_catalog(mutate(RULES_FILE, 3, "value_min", "fifty"))
    assert (RULES_FILE, 3, "value_min") in keys(cat)


def test_missing_header_column_blocks_only_that_file(mutate):
    d = mutate(CROPS_FILE, 2, "crop_id", "crop_a")  # ensure copy exists
    p = d / RULES_FILE
    text = p.read_text().replace("rule_type,", "ruletype,", 1)
    p.write_text(text)
    cat = load_catalog(d)
    assert (RULES_FILE, 1, "header") in keys(cat)
    assert cat.rules == [] and len(cat.crops) == 2


def test_missing_file(tmp_path):
    cat = load_catalog(tmp_path)
    assert {(i.file, i.field) for i in cat.errors} == {
        (CROPS_FILE, "file"),
        (RULES_FILE, "file"),
        (FERTILIZERS_FILE, "file"),
    }


# ------------------------------------------------------------------ index


def test_index_lookups():
    idx = CatalogIndex(load_catalog())
    assert idx.crop("soybean").crop_role == "cash_crop"
    assert idx.crop("nope") is None
    assert {r.rule_id for r in idx.rules_by_type("termination_timing")} >= {"cr_tt_03", "cr_tt_04"}
    assert {r.rule_id for r in idx.rules_for_crop("winter_wheat")} == {"ww_rc_01"}
    assert {r.rule_id for r in idx.rules_with_previous_crop("crimson_clover")} == {
        "fc_nut_03",
        "sb_rc_02",
    }
    assert {"cr_tt_03", "cr_tt_04"} <= {r.rule_id for r in idx.rules_with_next_crop("soybean")}
    assert idx.rule("fc_pw_03").production_system == "organic"
    assert {r.rule_id for r in idx.rules_for_production_system("Organic")} == {
        "fc_pw_03",
        "fc_pw_04",
    }
    assert {r.rule_id for r in idx.rules_for_region("nc piedmont")} >= {"fc_pw_03", "cr_pw_01"}
    both = idx.rules_matching(
        crop_id="cereal_rye", rule_type="termination_timing", next_crop_id="soybean"
    )
    assert [r.rule_id for r in both] == ["cr_tt_03", "cr_tt_04", "cr_tt_05"]
