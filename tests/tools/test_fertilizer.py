import pytest

from fieldshift.catalogs import V1_CATALOG_DIR, CatalogIndex, load_catalog
from fieldshift.tools.fertilizer import Product, calculate, parse_grade


@pytest.fixture(scope="module")
def index():
    return CatalogIndex(load_catalog())


@pytest.fixture(scope="module")
def index_v1_fert():
    return CatalogIndex(load_catalog(V1_CATALOG_DIR))


UREA = Product(fertilizer_id="urea_46_0_0")


def test_120_lb_n_with_urea_is_260_9_lb_product(index):
    r = calculate({"n_lb_per_acre": 120}, UREA, index, area_acres=10)
    assert r.status == "complete"
    assert r.product_lb_per_acre == 260.9
    assert r.product_lb_per_acre_exact == pytest.approx(120 / 0.46)
    n = r.nutrients[0]
    assert n.outcome == "met" and n.delivered_lb_per_acre == pytest.approx(120.0, abs=0.01)
    assert r.total_product_lb == pytest.approx(2608.7, abs=0.1)
    assert r.total_product_short_tons == pytest.approx(1.304, abs=0.001)
    assert r.derivation == "calculation"


def test_p_target_with_urea_is_a_supplies_no_p2o5_result_not_a_crash(index):
    r = calculate({"p2o5_lb_per_acre": 60}, UREA, index)
    assert r.status == "invalid_input"
    assert r.issues[0].code == "product_supplies_none"
    assert r.issues[0].field == "targets.p2o5_lb_per_acre"
    assert "product supplies no P2O5" in r.issues[0].message
    assert r.product_lb_per_acre is None


def test_zero_target_for_a_zero_content_nutrient_is_fine(index):
    r = calculate({"n_lb_per_acre": 46, "p2o5_lb_per_acre": 0}, UREA, index)
    assert r.status == "complete" and r.product_lb_per_acre == 100.0
    p = next(n for n in r.nutrients if n.nutrient == "p2o5")
    assert p.target_lb_per_acre == 0 and p.delivered_lb_per_acre == 0 and p.outcome == "met"


def test_multiple_targets_set_by_a_basis_nutrient_and_show_the_tradeoff(index):
    mes = Product(fertilizer_id="mes10_12_40_0")
    r = calculate({"n_lb_per_acre": 60, "p2o5_lb_per_acre": 40}, mes, index)
    assert r.basis_nutrient == "n" and r.product_lb_per_acre == 500.0
    n, p, k = r.nutrients
    assert (n.outcome, p.outcome, k.outcome) == ("met", "excess", "not_requested")
    assert p.delivered_lb_per_acre == 200 and p.difference_lb_per_acre == 160
    assert p.rate_alone_lb_product_per_acre == 100.0
    assert any("one rate" in x for x in r.notes) and any("blend" in x for x in r.notes)
    assert any("10S" in x for x in r.notes)  # sulfur in the grade is noted, not computed
    by_p = calculate({"n_lb_per_acre": 60, "p2o5_lb_per_acre": 40}, mes, index, basis="p2o5")
    assert by_p.product_lb_per_acre == 100.0 and by_p.nutrients[0].outcome == "shortfall"
    assert by_p.nutrients[0].difference_lb_per_acre == -48.0


def test_micronutrient_suffix_is_noted_not_computed(index):
    r = calculate({"p2o5_lb_per_acre": 40}, Product(fertilizer_id="mesz_12_40_0"), index)
    assert any("1Zn" in x for x in r.notes)
    assert r.product_lb_per_acre == 100.0


def test_grower_entered_grade(index):
    r = calculate({"k2o_lb_per_acre": 90}, Product(grade="0-0-60", name="my potash"), index)
    assert r.product_lb_per_acre == 150.0 and r.product.source == "grower"
    assert any("entered by the grower" in x for x in r.notes)
    bad = calculate({"n_lb_per_acre": 10}, Product(grade="abc"), index)
    assert bad.issues[0].field == "product.grade"
    over = calculate({"n_lb_per_acre": 10}, Product(grade="60-60-60"), index)
    assert over.issues[0].code == "grade_range"


def test_never_invents_an_n_rate(index):
    r = calculate({}, UREA, index, crop_id="field_corn")
    assert r.status == "invalid_input" and r.issues[0].code == "no_target"
    assert any("fc_nut_01" in n for n in r.notes)
    # a non-N target on corn still reminds the user there is no automatic N rate
    k = calculate(
        {"k2o_lb_per_acre": 60}, Product(fertilizer_id="mop_0_0_60"), index, crop_id="soybean"
    )
    assert k.status == "complete" and any("sb_nut_01" in n for n in k.notes)
    assert all(n.nutrient != "n" or n.outcome == "not_requested" for n in k.nutrients)


@pytest.mark.parametrize(
    ("targets", "field"),
    [({"n_lb_per_acre": -5}, "targets.n_lb_per_acre"),
     ({"n_lb_per_acre": float("nan")}, "targets.n_lb_per_acre"),
     ({"n_lb_per_acre": "lots"}, "targets.n_lb_per_acre"),
     ({"n_lb_per_acre": True}, "targets.n_lb_per_acre"),
     ({"nitrogen": 5}, "targets.nitrogen")],
)  # fmt: skip
def test_bad_targets(index, targets, field):
    r = calculate(targets, UREA, index)
    # True is treated as "not requested" (a bool is not a number): the request then has no target
    assert r.status == "invalid_input"
    assert r.issues[0].field in (field, "targets")


def test_bad_area_basis_and_product(index):
    assert (
        calculate({"n_lb_per_acre": 1}, UREA, index, area_acres=0).issues[0].field == "area_acres"
    )
    assert calculate({"n_lb_per_acre": 1}, UREA, index, basis="k2o").issues[0].field == "basis"
    assert (
        calculate({"n_lb_per_acre": 1}, Product(fertilizer_id="nope"), index).issues[0].code
        == "unknown_product"
    )
    assert calculate({"n_lb_per_acre": 1}, Product(), index).issues[0].code == "product_required"


def test_parse_grade():
    assert parse_grade("12-40-0-10S-1Zn") == (12.0, 40.0, 0.0, "10S-1Zn")
    assert parse_grade("46-0-0") == (46.0, 0.0, 0.0, None)
    assert parse_grade("46-0") is None


def test_huge_or_overflowing_numbers_are_typed_errors_not_500s_or_nulls(index):
    for bad in (10**400, 1e308, 1e12):
        r = calculate({"n_lb_per_acre": bad}, UREA, index)
        assert r.status == "invalid_input" and r.issues[0].field.startswith("targets")
    r = calculate({"n_lb_per_acre": 1}, UREA, index, area_acres=10**400)
    assert r.status == "invalid_input" and r.issues[0].field == "area_acres"


def test_nutrient_lines_use_outcome_not_status(index):
    r = calculate({"n_lb_per_acre": 60}, UREA, index)
    assert not hasattr(r.nutrients[0], "status") and r.nutrients[0].outcome == "met"


def test_tiny_grades_and_overflowing_results_are_typed_errors(index):
    for grade in ("0.000000001-0-0", "0.0001-0-0"):
        r = calculate({"n_lb_per_acre": 100}, Product(grade=grade), index)
        assert r.status == "invalid_input" and r.issues[0].code == "grade_range"
    ok = calculate({"n_lb_per_acre": 1}, Product(grade="0.01-0-0"), index)
    assert ok.status == "complete" and ok.product_lb_per_acre == 10000.0
    big = calculate({"n_lb_per_acre": 99999}, Product(grade="0.01-0-0"), index, area_acres=9e6)
    assert big.status == "invalid_input"


# ------------------------------------------------------------------ catalog v2 N reference


def test_corn_n_reference_is_shown_but_never_used_as_the_target(index):
    r = calculate(
        {"p2o5_lb_per_acre": 40},
        Product(fertilizer_id="mes10_12_40_0"),
        index,
        crop_id="field_corn",
    )
    assert r.n_reference.rule_id == "fc_nut_01"
    assert (r.n_reference.value_min, r.n_reference.value_max) == (120.0, 160.0)
    assert r.n_reference.is_grower_target is False and "not your target" in r.n_reference.label
    assert any("120-160 lb N/ac" in n and "not your target" in n for n in r.notes)
    # the calculation ignored it: only the P2O5 target set the rate
    assert r.product_lb_per_acre == 100.0 and r.basis_nutrient == "p2o5"
    n_line = next(x for x in r.nutrients if x.nutrient == "n")
    assert n_line.outcome == "not_requested" and n_line.target_lb_per_acre is None


def test_no_target_still_errors_but_carries_the_reference(index):
    r = calculate({}, UREA, index, crop_id="field_corn")
    assert r.status == "invalid_input" and r.issues[0].code == "no_target"
    assert r.n_reference.value_min == 120.0 and r.product_lb_per_acre is None


@pytest.mark.parametrize(
    ("target", "pos"), [(100, "below"), (120, "within"), (160, "within"), (200, "above")]
)
def test_grower_target_is_compared_to_the_reference_not_replaced_by_it(index, target, pos):
    r = calculate({"n_lb_per_acre": target}, UREA, index, crop_id="field_corn")
    assert r.target_vs_reference.position == pos
    assert r.product_lb_per_acre == round(target / 0.46, 1)  # rate comes from the grower's target
    assert "does not replace your soil-test target" in r.target_vs_reference.text


def test_soybean_reference_zero_is_a_real_zero(index):
    r = calculate({"n_lb_per_acre": 30}, UREA, index, crop_id="soybean")
    assert r.n_reference.value_min == 0.0 and r.n_reference.value_min is not None
    assert r.target_vs_reference.position == "above"
    zero = calculate(
        {"n_lb_per_acre": 0, "k2o_lb_per_acre": 60},
        Product(fertilizer_id="mop_0_0_60"),
        index,
        crop_id="soybean",
    )
    assert zero.target_vs_reference.position == "equal" and zero.product_lb_per_acre == 100.0


def test_v1_has_no_n_numbers_so_the_old_wording_applies(index_v1_fert):
    r = calculate(
        {"k2o_lb_per_acre": 60},
        Product(fertilizer_id="mop_0_0_60"),
        index_v1_fert,
        crop_id="field_corn",
    )
    assert r.n_reference is None and any("supplies no automatic nitrogen" in n for n in r.notes)


def test_other_crops_get_no_reference(index):
    assert calculate({"n_lb_per_acre": 10}, UREA, index, crop_id="cereal_rye").n_reference is None
