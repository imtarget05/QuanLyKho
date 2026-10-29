"""CWE-1236 — exported CSV cells must never be executable spreadsheet formulas.

A value beginning with ``=`` ``+`` ``-`` ``@`` TAB or CR is interpreted as a
formula by Excel / Google Sheets. `etl._csv_safe` must neutralise those leads
while leaving plain numbers (including negatives) untouched.
"""

import pytest

from app.features.etl.routes import _csv_safe


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("=cmd|'/c calc'!A1", "'=cmd|'/c calc'!A1"),
        ("@SUM(A1:A9)", "'@SUM(A1:A9)"),
        ("+1", "'+1"),
        ("-1+1", "'-1+1"),
        ("\tHIDDEN", "'\tHIDDEN"),
        ("\rHIDDEN", "'\rHIDDEN"),
        # untouched
        ("SKU-001", "SKU-001"),
        ("Kho trung tâm", "Kho trung tâm"),
        ("-1234", "-1234"),
        ("-1000.50", "-1000.50"),
        ("", ""),
    ],
)
def test_csv_safe_neutralises_formula_leads(raw: str, expected: str) -> None:
    assert _csv_safe(raw) == expected


def test_csv_safe_handles_non_string_and_none() -> None:
    assert _csv_safe(12) == "12"
    assert _csv_safe(None) == ""
