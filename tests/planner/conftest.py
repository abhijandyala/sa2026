import pytest

from fieldshift.catalogs import V1_CATALOG_DIR, CatalogIndex, load_catalog


@pytest.fixture(scope="session")
def index() -> CatalogIndex:
    return CatalogIndex(load_catalog())


@pytest.fixture(scope="session")
def index_v1() -> CatalogIndex:
    """The v1 catalog, for regressions that depend on its gaps (no wheat rows)."""
    return CatalogIndex(load_catalog(V1_CATALOG_DIR))
