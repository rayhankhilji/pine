from decimal import Decimal

from pine.ingest.spreadsheet import infer_column_types, parse


def test_xlsx_two_sheets(xlsx_two_sheets: bytes) -> None:
    result = parse(xlsx_two_sheets, "financials.xlsx")
    assert len(result.pages) == 2
    assert result.pages[0].sheet_name == "P&L"
    assert result.pages[1].sheet_name == "Balance"
    table = result.pages[0].tables[0]
    assert table.n_rows == 3
    assert table.n_cols == 3
    assert table.column_types[1] == "number"
    cells = {(c.row, c.col): c for c in table.cells}
    assert cells[(1, 1)].value_num == Decimal("4100000")
    assert cells[(1, 1)].ref == "B2"


def test_csv_parse() -> None:
    data = b"customer,arr\nAcme,$2,244,000\nBeta,$500,000\n".replace(b"$2,244,000", b"2244000")
    result = parse(data, "customers.csv")
    table = result.pages[0].tables[0]
    assert table.n_rows == 3
    assert table.column_types[1] in {"number", "currency"}


def test_tsv_parse() -> None:
    result = parse(b"a\tb\n1\t2\n", "data.tsv")
    assert result.pages[0].tables[0].n_cols == 2


def test_column_type_inference() -> None:
    rows = [
        ["name", "revenue", "pct", "when"],
        ["a", "$100", "10%", "2025-01-01"],
        ["b", "$200", "20%", "2025-02-01"],
        ["c", "$300", "30%", "2025-03-01"],
    ]
    types = infer_column_types(rows, 0)
    assert types == ["text", "currency", "percent", "date"]


def test_xls_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse(b"old", "file.xls")
