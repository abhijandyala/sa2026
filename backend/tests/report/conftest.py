import pytest

from fieldshift.api.samples import load_samples
from fieldshift.compare.context import get_context

YEAR = 2027  # explicit: results never depend on today's date


@pytest.fixture(scope="session")
def ctx():
    return get_context()


@pytest.fixture(scope="session")
def rye():
    return load_samples().plans["corn_soy__rye"].plan


def edited(plan, **winter):
    return plan.model_copy(update={"winter": plan.winter.model_copy(update=winter)})
