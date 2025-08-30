from dataclasses import dataclass
from typing import Optional, Dict, List, Any
import datetime as dt
import xml.etree.ElementTree as ET


@dataclass
class FundamentalsDTO:
    symbol: str
    as_of: dt.datetime
    source: str  # "IBKR" or similar
    report_types_used: List[str]
    company: Dict[str, Optional[str]]
    statements: Dict[str, Optional[float]]
    ratios: Dict[str, Optional[float]]
    cap_table: Dict[str, Optional[float]]


def _to_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}
    try:
        return float(text)
    except ValueError:
        suffix = text[-1]
        if suffix in mult:
            try:
                return float(text[:-1]) * mult[suffix]
            except ValueError:
                return None
    return None


async def fetch_fundamentals(ib, contract) -> FundamentalsDTO:
    snapshot_xml = await _fetch_report_snapshot(ib, contract)
    financials_xml = await _fetch_financial_statements(ib, contract)
    snap = _parse_snapshot(snapshot_xml, contract.symbol)
    fin = _parse_financials(financials_xml, contract.symbol)
    return _normalize(snap, fin)


async def _fetch_report_snapshot(ib, contract) -> str:  # pragma: no cover - network
    return await ib.reqFundamentalDataAsync(contract, "ReportSnapshot")


async def _fetch_financial_statements(ib, contract) -> str:  # pragma: no cover - network
    return await ib.reqFundamentalDataAsync(contract, "FinancialStatements")


def _parse_snapshot(xml: str, symbol: str) -> Dict[str, Any]:
    root = ET.fromstring(xml)
    company_node = root.find("Company") or ET.Element("Company")
    ratios_node = root.find("Ratios") or ET.Element("Ratios")
    cap_node = root.find("CapTable") or ET.Element("CapTable")

    company = {
        "name": company_node.findtext("Name"),
        "sector": company_node.findtext("Sector"),
        "industry": company_node.findtext("Industry"),
        "exchange": company_node.findtext("Exchange"),
        "currency": company_node.findtext("Currency"),
        "country": company_node.findtext("Country"),
        "cik": company_node.findtext("CIK"),
    }

    ratios = {
        "pe_ttm": _to_float(ratios_node.findtext("PERatioTTM")),
        "forward_pe": _to_float(ratios_node.findtext("ForwardPERatio")),
        "roe": _to_float(ratios_node.findtext("ROE")),
        "roc": _to_float(ratios_node.findtext("ROC")),
        "roa": _to_float(ratios_node.findtext("ROA")),
        "price_to_book": _to_float(ratios_node.findtext("PriceToBook")),
        "book_value_ps": _to_float(ratios_node.findtext("BookValuePerShare")),
        "cash_ps": _to_float(ratios_node.findtext("CashPerShare")),
        "ev_to_ebitda": _to_float(ratios_node.findtext("EVToEBITDA")),
        "beta": _to_float(ratios_node.findtext("Beta")),
    }

    cap_table = {
        "market_cap": _to_float(cap_node.findtext("MarketCap")),
        "shares_outstanding": _to_float(cap_node.findtext("SharesOutstanding")),
        "float_shares": _to_float(cap_node.findtext("FloatShares")),
    }

    return {
        "symbol": symbol,
        "company": company,
        "ratios": ratios,
        "cap_table": cap_table,
    }


def _parse_financials(xml: str, symbol: str) -> Dict[str, Any]:
    root = ET.fromstring(xml)
    income = root.find("IncomeStatement") or ET.Element("IncomeStatement")
    dividends = root.find("Dividends") or ET.Element("Dividends")

    statements = {
        "eps_ttm": _to_float(income.findtext("EPS")),
        "eps_q": _to_float(income.findtext("EPSQ")),
        "revenue_ttm": _to_float(income.findtext("RevenueTTM")),
        "revenue_q": _to_float(income.findtext("RevenueQ")),
        "dividend_ttm": _to_float(dividends.findtext("DividendTTM")),
        "dividend_q": _to_float(dividends.findtext("DividendQ")),
        "dividend_yield": _to_float(dividends.findtext("DividendYield")),
        "payout_ratio": _to_float(dividends.findtext("PayoutRatio")),
    }

    return {"symbol": symbol, "statements": statements}


def _normalize(snap: Dict[str, Any], fin: Dict[str, Any]) -> FundamentalsDTO:
    as_of = dt.datetime.utcnow()
    return FundamentalsDTO(
        symbol=snap.get("symbol"),
        as_of=as_of,
        source="IBKR",
        report_types_used=["ReportSnapshot", "FinancialStatements"],
        company=snap.get("company", {}),
        statements=fin.get("statements", {}),
        ratios=snap.get("ratios", {}),
        cap_table=snap.get("cap_table", {}),
    )
