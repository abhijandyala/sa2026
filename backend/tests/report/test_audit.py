import pytest

from fieldshift.report.audit import (
    AuditBook,
    AuditError,
    bare_numbers,
    finalize,
    source_ref,
    verify,
)

REF = source_ref("calculation", "test")


def test_number_is_an_object_with_a_stable_audit_id():
    b = AuditBook()
    a = b.num(12, "days", "calculation", REF, {"x": 1})
    again = b.num(12, "days", "calculation", REF, {"x": 1})
    other = b.num(12, "days", "calculation", REF, {"x": 2})
    assert a == again and a["audit_id"] != other["audit_id"]
    assert set(a) == {"value", "unit", "audit_id"} and a["value"] == 12
    assert b.as_dict()["count"] == 2


def test_missing_value_is_none_not_a_number():
    assert AuditBook().num(None, "mm", "nasa", REF) is None


def test_real_zero_is_audited_as_zero():
    n = AuditBook().num(0, "days", "calculation", REF)
    assert n["value"] == 0 and n["value"] is not None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "7"])
def test_non_finite_or_non_numeric_values_are_rejected(bad):
    with pytest.raises(AuditError):
        AuditBook().num(bad, "mm", "nasa", REF)


def test_unknown_derivation_is_rejected():
    with pytest.raises(AuditError):
        AuditBook().num(1, "mm", "guess", REF)


def test_finalize_stringifies_years_and_flags_other_bare_numbers():
    b = AuditBook()
    tree = {
        "year": 2025,
        "dry_years": [1981, 1983],
        "n": 5,
        "ok": b.num(1, "x", "calculation", REF),
    }
    out = finalize(tree, b)
    assert out["year"] == "2025" and out["dry_years"] == ["1981", "1983"]
    assert out["n"]["audit_id"] and b.as_dict()["unclassified"] == 1


def test_verify_finds_bare_numbers_missing_entries_and_tampering():
    b = AuditBook()
    good = {"a": b.num(3, "mm", "nasa", REF)}
    note = {**good, "audit": b.as_dict()}
    assert verify(note) == []
    assert verify({**note, "stray": 4})[0].startswith("bare number at stray")
    tampered = {"a": {**good["a"], "value": 99}, "audit": b.as_dict()}
    assert "differ from audit entry" in verify(tampered)[0]
    assert (
        "no entry"
        in verify({"a": {"value": 1, "unit": "x", "audit_id": "zzz"}, "audit": b.as_dict()})[0]
    )
    assert list(bare_numbers({"x": [1, {"y": 2.5}], "s": "1", "b": True, "n": None})) == [
        ("x[0]", 1),
        ("x[1].y", 2.5),
    ]
