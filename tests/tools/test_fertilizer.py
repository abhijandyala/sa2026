import pytest

from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.tools.fertilizer import Product, calculate, parse_grade


@pytest.fixture(scope="module")
def index():
    return CatalogIndex(load_catalog())


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
