"""Two-period (earlier vs recent) descriptive comparison with honest denominators.

Constants (documented, tested):

* ``EARLIER`` = 1981-2000 and ``RECENT`` = 2006-2025, 20 planting years each.
* 2001-2005 is in neither era (those years stay in the full record and in replay).
* ``MIN_EVALUABLE_PER_ERA`` = 15: each era needs at least 15 of its 20 seasons evaluable, or the
  result is ``insufficient_data``.
* ``SIMILARITY_BAND_PP`` = 10.0: ``|recent% - earlier%| < 10`` percentage points is ``similar``;
  a difference of exactly 10 counts as more/less frequent.
* An indicator is a per-season yes/no event. A season that cannot be evaluated is ``None`` (with a
  reason) and is excluded from that era's denominator, never counted as "no event".

The comparison never makes a trend, cause or forecast claim; each label ships with fixed text.
Every output carries the single frozen ``ThresholdSet`` it was computed from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from pydantic import BaseModel, ConfigDict, Field

from fieldshift.contracts import Status, ThresholdSet

EARLIER = (1981, 2000)
RECENT = (2006, 2025)
EXCLUDED_FROM_ERAS = (2001, 2002, 2003, 2004, 2005)
MIN_EVALUABLE_PER_ERA = 15
SIMILARITY_BAND_PP = 10.0

MORE = "more_frequent_recent"
LESS = "less_frequent_recent"
SIMILAR = "similar"
INSUFFICIENT = "insufficient_data"

LABEL_TEXT = {
    MORE: "This happened in a larger share of seasons in 2006-2025 than in 1981-2000. "
    "Descriptive comparison of two periods only; not a trend, cause, or forecast.",
    LESS: "This happened in a smaller share of seasons in 2006-2025 than in 1981-2000. "
    "Descriptive comparison of two periods only; not a trend, cause, or forecast.",
    SIMILAR: "The share of seasons is similar in 1981-2000 and 2006-2025 "
    f"(within {SIMILARITY_BAND_PP:g} percentage points). "
    "Descriptive comparison of two periods only; not a trend, cause, or forecast.",
    INSUFFICIENT: f"At least {MIN_EVALUABLE_PER_ERA} evaluable seasons are needed in each period; "
    "one or both periods have fewer, so no comparison is made.",
}


@dataclass(frozen=True)
class YearOutcome:
    """One season's yes/no for an indicator. ``event`` is ``None`` when not evaluable."""

    event: bool | None
    reason: str | None = None


Indicator = Mapping[int, YearOutcome]


class MissingYear(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int
    reason: str


class EraStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int
    end: int
    seasons: int  # planting years in the era (20)
    evaluable: int  # denominator
    events: int  # numerator
    pct: float | None  # events / evaluable * 100, 1 decimal; None when evaluable == 0
    not_evaluable: list[MissingYear]
    threshold_value: float | None = None  # the one frozen cutoff used (if the indicator has one)


class EraComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    indicator: str
    status: Status  # complete | insufficient_data
    result: str  # more_frequent_recent | less_frequent_recent | similar | insufficient_data
    earlier: EraStats
    recent: EraStats
    diff_pp: float | None
    similarity_band_pp: float = SIMILARITY_BAND_PP
    min_evaluable_per_era: int = MIN_EVALUABLE_PER_ERA
    threshold_set_id: str
    thresholds: dict[str, float | None]
    basis: str = "own_evaluable_seasons"  # or "shared_evaluable_seasons"
    excluded_from_eras: list[int] = Field(default_factory=lambda: list(EXCLUDED_FROM_ERAS))
    caveat: str


def _pct(events: int, evaluable: int) -> Fraction | None:
    return Fraction(events * 100, evaluable) if evaluable else None


def _era(
    indicator: Indicator, span: tuple[int, int], threshold_value: float | None
) -> tuple[EraStats, Fraction | None]:
    years = range(span[0], span[1] + 1)
    events = evaluable = 0
    missing: list[MissingYear] = []
    for y in years:
        outcome = indicator.get(y)
        if outcome is None:
            missing.append(MissingYear(year=y, reason="no_result_for_year"))
        elif outcome.event is None:
            missing.append(MissingYear(year=y, reason=outcome.reason or "not_evaluable"))
        else:
            evaluable += 1
            events += bool(outcome.event)
    exact = _pct(events, evaluable)
    stats = EraStats(
        start=span[0], end=span[1], seasons=len(years), evaluable=evaluable, events=events,
        pct=round(float(exact), 1) if exact is not None else None,
        not_evaluable=missing, threshold_value=threshold_value,
    )
    return stats, exact


def compare_eras(
    name: str,
    indicator: Indicator,
    thresholds: ThresholdSet,
    *,
    threshold_names: Iterable[str] = (),
    basis: str = "own_evaluable_seasons",
) -> EraComparison:
    """Compare the earlier and recent eras for one indicator.

    ``threshold_names`` lists the entries of ``thresholds`` that define the indicator (for
    example the heavy-rain value or the spring dry cutoff). They are reported once and echoed
    in both eras, proving both used the same frozen value.
    """
    used = {n: thresholds.get(n).value for n in threshold_names}
    single = next(iter(used.values())) if len(used) == 1 else None
    earlier, e_exact = _era(indicator, EARLIER, single)
    recent, r_exact = _era(indicator, RECENT, single)
    enough = (
        earlier.evaluable >= MIN_EVALUABLE_PER_ERA and recent.evaluable >= MIN_EVALUABLE_PER_ERA
    )
    if not enough:
        return EraComparison(
            indicator=name, status=Status.INSUFFICIENT_DATA, result=INSUFFICIENT,
            earlier=earlier, recent=recent, diff_pp=None,
            threshold_set_id=thresholds.threshold_set_id, thresholds=used, basis=basis,
            caveat=LABEL_TEXT[INSUFFICIENT],
        )
    assert e_exact is not None and r_exact is not None
    diff = r_exact - e_exact
    band = Fraction(str(SIMILARITY_BAND_PP))
    result = SIMILAR if abs(diff) < band else (MORE if diff > 0 else LESS)
    return EraComparison(
        indicator=name, status=Status.COMPLETE, result=result, earlier=earlier, recent=recent,
        diff_pp=round(float(diff), 1), threshold_set_id=thresholds.threshold_set_id,
        thresholds=used, basis=basis, caveat=LABEL_TEXT[result],
    )


# --------------------------------------------------------------------------- indicator builders


def dry_spring_indicator(spring_by_year: Mapping[int, object]) -> dict[int, YearOutcome]:
    """Event = the 30-day spring window is dry (``SpringResult.is_dry``)."""
    out: dict[int, YearOutcome] = {}
    for year, res in spring_by_year.items():
        dry = getattr(res, "is_dry", None)
        out[year] = YearOutcome(
            dry, None if dry is not None else _reason(res, "spring_not_evaluable")
        )
    return out


def winter_heavy_rain_indicator(winter_by_year: Mapping[int, object]) -> dict[int, YearOutcome]:
    """Event = at least one heavy-rain day fell outside planned living cover that winter."""
    out: dict[int, YearOutcome] = {}
    for year, res in winter_by_year.items():
        n = getattr(res, "heavy_rain_days_outside_cover", None)
        out[year] = YearOutcome(
            None if n is None else n > 0, None if n is not None else _reason(res, "winter_not_evaluable")
        )
    return out


def check_indicator(evaluations: Iterable[object], rule_id: str) -> dict[int, YearOutcome]:
    """Event = a rule check flagged that season (``SeasonEvaluation`` from the rule engine)."""
    out: dict[int, YearOutcome] = {}
    for ev in evaluations:
        year = ev.year  # type: ignore[attr-defined]
        check = ev.check(rule_id)  # type: ignore[attr-defined]
        if check is None:
            out[year] = YearOutcome(None, "rule_not_evaluated")
        elif check.status == Status.COMPLETE:
            out[year] = YearOutcome(bool(check.flagged))
        else:
            out[year] = YearOutcome(None, f"{check.status}: {check.reason}")
    return out


def any_of(indicators: Iterable[Indicator]) -> dict[int, YearOutcome]:
    """Combine indicators so each season counts once: True if any component fired."""
    parts = list(indicators)
    years = sorted({y for p in parts for y in p})
    out: dict[int, YearOutcome] = {}
    for y in years:
        outcomes = [p.get(y) for p in parts]
        if any(o is not None and o.event for o in outcomes):
            out[y] = YearOutcome(True)
        elif all(o is not None and o.event is False for o in outcomes):
            out[y] = YearOutcome(False)
        else:
            reason = next((o.reason for o in outcomes if o is None or o.event is None), None)
            out[y] = YearOutcome(None, (reason if reason else "component_not_evaluable"))
    return out


def _reason(res: object, default: str) -> str:
    reasons = getattr(res, "reasons", None) or []
    return reasons[0] if reasons else default


# --------------------------------------------------------------------------- cross-plan helpers


def shared_years(indicators: Mapping[str, Indicator]) -> set[int]:
    """Years evaluable (event not None) for every plan."""
    sets = [
        {y for y, o in ind.items() if o.event is not None} for ind in indicators.values()
    ]
    return set.intersection(*sets) if sets else set()


def restrict_to_years(indicator: Indicator, years: set[int]) -> dict[int, YearOutcome]:
    return {
        y: (o if y in years else YearOutcome(None, "not_evaluable_for_every_compared_plan"))
        for y, o in indicator.items()
    }


def compare_plans_eras(
    name: str,
    indicators: Mapping[str, Indicator],
    thresholds: ThresholdSet,
    *,
    threshold_names: Iterable[str] = (),
) -> dict[str, EraComparison]:
    """Era comparison for several plans on the SAME complete years (shared-year basis).

    Each result is labelled ``shared_evaluable_seasons`` so a reader can see the denominator
    was narrowed to the years every plan could be evaluated for.
    """
    years = shared_years(indicators)
    return {
        pid: compare_eras(
            name, restrict_to_years(ind, years), thresholds,
            threshold_names=threshold_names, basis="shared_evaluable_seasons",
        )
        for pid, ind in indicators.items()
    }
