"""Helpers: copy the synthetic fixture catalog and mutate a single cell."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

FIXTURE_BASE = Path(__file__).resolve().parents[1] / "fixtures" / "catalogs" / "base"


@pytest.fixture
def base_dir() -> Path:
    return FIXTURE_BASE


@pytest.fixture
def mutate(tmp_path):
    """mutate(file, row, field, value) -> catalog dir. ``row`` is the spreadsheet row (header=1)."""

    def _mutate(file: str, row: int, field: str, value: str, *, copy_row_from: int | None = None):
        d = tmp_path / "cat"
        if not d.exists():
            shutil.copytree(FIXTURE_BASE, d)
        path = d / file
        with path.open(newline="") as f:
            rows = list(csv.reader(f))
        header = rows[0]
        if copy_row_from is not None:  # append a copy of an existing row
            rows.append(list(rows[copy_row_from - 1]))
            row = len(rows)
        rows[row - 1][header.index(field)] = value
        with path.open("w", newline="") as f:
            csv.writer(f).writerows(rows)
        return d

    return _mutate
