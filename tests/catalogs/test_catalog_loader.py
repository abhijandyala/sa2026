from fieldshift.catalogs import (
    DEFAULT_CATALOG_DIR,
    V1_CATALOG_DIR,
    V2_CATALOG_DIR,
    CatalogIndex,
    load_catalog,
)
from fieldshift.catalogs.validate import (
    CROPS_FILE,
    FERTILIZERS_FILE,
    RULES_FILE,
    parse_mm_dd,
)


def keys(catalog, severity="error"):
    return {(i.file, i.row, i.field) for i in catalog.issues if i.severity == severity}


# ------------------------------------------------------------------ real v1 catalogs (regression)


def test_v1_loads_with_only_the_two_blank_verified_date_warnings():
    cat = load_catalog(V1_CATALOG_DIR)
    assert cat.errors == []
    assert len(cat.crops) == 5
    assert len(cat.rules) == 85
    assert len(cat.fertilizers) == 5
    assert {(i.file, i.field, i.severity) for i in cat.issues} == {
        (RULES_FILE, "verified_date", "warning")
    }
    assert sorted(cat.rule_ids_with_warning("verified_blank")) == ["fc_nut_01", "sb_nut_01"]


def test_v1_blank_verified_rows_are_kept_as_data_without_auto_n_rate():
    cat = load_catalog(V1_CATALOG_DIR)
    idx = CatalogIndex(cat)
    for rid in ("fc_nut_01", "sb_nut_01"):
        r = idx.rule(rid)
        assert r is not None
        assert r.verified_date is None
        assert r.value_min is None and r.value_max is None and r.operator is None


def test_exposure_duration_several_is_kept_qualitative():
    r = CatalogIndex(load_catalog(V1_CATALOG_DIR)).rule("sb_wt_02")
    assert r.exposure_duration is None
    assert r.exposure_duration_text == "several"
    assert r.exposure_unit == "days"


def test_blank_is_none_and_real_zero_stays_zero():
    cat = load_catalog(V1_CATALOG_DIR)
    urea = next(f for f in cat.fertilizers if f.fertilizer_id == "urea_46_0_0")
    assert urea.p2o5_pct == 0 and urea.p2o5_pct is not None
    fc_pw_01 = CatalogIndex(cat).rule("fc_pw_01")
    assert fc_pw_01.value_max is None  # blank, not 0
    assert fc_pw_01.window_start_mm_dd is None


def test_manifest_has_hashes_and_row_counts():
    m = load_catalog(V1_CATALOG_DIR).manifest
    assert m.version == "v1"
    assert m.files[RULES_FILE].rows == 85 and m.files[RULES_FILE].usable_rows == 85
    assert m.files[RULES_FILE].warnings == 2
    assert len(m.files[RULES_FILE].sha256) == 64
    assert load_catalog(V1_CATALOG_DIR).manifest.content_hash == m.content_hash  # deterministic


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
    idx = CatalogIndex(load_catalog(V1_CATALOG_DIR))
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


# ------------------------------------------------------------------ review fixes (phase-0-B)


def test_rule_referencing_a_rejected_crop_is_dangling(mutate):
    # crop_b (row 3) fails validation, so fx_03 (cover crop rule on crop_b) must not stay usable.
    cat = load_catalog(mutate(CROPS_FILE, 3, "crop_role", "weed"))
    assert (CROPS_FILE, 3, "crop_role") in keys(cat)
    assert (RULES_FILE, 4, "crop_id") in keys(cat)
    assert "fx_03" not in {r.rule_id for r in cat.rules}
    assert all(r.crop_id in {c.crop_id for c in cat.crops} for r in cat.rules)


def test_nonfinite_numbers_are_rejected(mutate):
    d = mutate(RULES_FILE, 3, "value_min", "nan")
    d = mutate(RULES_FILE, 4, "value_max", "inf")
    d = mutate(RULES_FILE, 4, "exposure_duration", "nan")
    cat = load_catalog(d)
    assert {
        (RULES_FILE, 3, "value_min"),
        (RULES_FILE, 4, "value_max"),
        (RULES_FILE, 4, "exposure_duration"),
    } <= keys(cat)
    assert {r.rule_id for r in cat.rules} == {"fx_01", "fx_04"}


def test_duplicate_header_columns_are_rejected(mutate):
    d = mutate(CROPS_FILE, 2, "crop_id", "crop_a")
    p = d / CROPS_FILE
    p.write_text(p.read_text().replace("common_name,", "crop_id,", 1))
    cat = load_catalog(d)
    assert (CROPS_FILE, 1, "header") in keys(cat)
    assert cat.crops == []


def test_crop_dropped_for_a_parse_error_also_orphans_its_rules(mutate):
    cat = load_catalog(mutate(CROPS_FILE, 3, "verified_date", "not-a-date"))
    assert (CROPS_FILE, 3, "verified_date") in keys(cat)
    assert (RULES_FILE, 4, "crop_id") in keys(cat)
    assert "fx_03" not in {r.rule_id for r in cat.rules}


# ------------------------------------------------------------------ catalog v2


def test_default_catalog_is_v2_and_v1_stays_loadable():
    assert DEFAULT_CATALOG_DIR == V2_CATALOG_DIR
    assert load_catalog().version == "v2" and load_catalog(V1_CATALOG_DIR).version == "v1"


def test_v2_loads_with_zero_errors_and_zero_warnings():
    cat = load_catalog(V2_CATALOG_DIR)
    assert cat.errors == [] and cat.issues == []
    assert (len(cat.crops), len(cat.rules), len(cat.fertilizers)) == (5, 98, 5)
    assert cat.manifest.files[RULES_FILE].rows == cat.manifest.files[RULES_FILE].usable_rows == 98


def test_v2_new_units_are_accepted_and_kept_verbatim():
    idx = CatalogIndex(load_catalog(V2_CATALOG_DIR))
    drilled, late = idx.rule("ww_v2_seed_drilled"), idx.rule("sb_v2_seed_late")
    assert (drilled.unit, drilled.value_min, drilled.value_max) == ("seeds/ft2", 30.0, 35.0)
    assert (late.unit, late.value_min, late.value_max) == ("seeds/acre", 165000.0, 175000.0)


def test_unknown_units_are_still_rejected(mutate):
    cat = load_catalog(mutate(RULES_FILE, 3, "unit", "seeds/hectare"))
    assert (RULES_FILE, 3, "unit") in keys(cat)


def test_v2_n_rate_rows_fc_nut_01_range_and_sb_nut_01_real_zero():
    idx = CatalogIndex(load_catalog(V2_CATALOG_DIR))
    fc, sb = idx.rule("fc_nut_01"), idx.rule("sb_nut_01")
    assert (fc.operator, fc.value_min, fc.value_max, fc.unit) == (
        "between", 120.0, 160.0, "lb_N_per_acre",
    )  # fmt: skip
    assert sb.operator == "eq" and sb.value_min == 0.0 and sb.value_min is not None
    assert sb.value_max is None  # blank stays None
    assert fc.verified_date is not None and sb.verified_date is not None


def test_v2_differs_from_v1_only_in_the_two_n_rows_plus_the_new_wheat_and_soybean_rows():
    v1 = {r.rule_id: r for r in load_catalog(V1_CATALOG_DIR).rules}
    v2 = {r.rule_id: r for r in load_catalog(V2_CATALOG_DIR).rules}
    assert set(v1) <= set(v2)
    changed = {rid for rid in v1 if v1[rid] != v2[rid]}
    assert changed == {"fc_nut_01", "sb_nut_01"}
    assert {rid for rid in v2 if rid not in v1} == {
        r for r in v2 if r.startswith(("ww_v2_", "sb_v2_"))
    }
