import pytest

from fieldshift.catalogs import CatalogIndex, load_catalog


@pytest.fixture(scope="session")
def index() -> CatalogIndex:
    return CatalogIndex(load_catalog())
