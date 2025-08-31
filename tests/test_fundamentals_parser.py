from pathlib import Path
import datetime as dt

from server.data.fundamentals.ibkr_fundamentals import (
    _parse_snapshot,
    _parse_financials,
    _normalize,
    FundamentalsDTO,
)


FIXTURES = Path(__file__).parent / "fixtures" / "fundamentals"


def test_parsers_produce_dto():
    snap_xml = (FIXTURES / "report_snapshot.xml").read_text()
    fin_xml = (FIXTURES / "financial_statements.xml").read_text()

    snap = _parse_snapshot(snap_xml, "AAPL")
    fin = _parse_financials(fin_xml, "AAPL")
    dto = _normalize(snap, fin)

    assert isinstance(dto, FundamentalsDTO)
    assert dto.symbol == "AAPL"
    assert dto.company["name"] == "Apple Inc"
    assert dto.statements["eps_ttm"] == 5.0
    assert dto.ratios["pe_ttm"] == 20.0
    assert dto.cap_table["market_cap"] == 2_000_000_000.0
    assert dto.as_of <= dt.datetime.utcnow()
