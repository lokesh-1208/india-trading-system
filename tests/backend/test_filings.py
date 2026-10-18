"""Checks reading NSE's result filings (XBRL) and building the yearly table."""

import pandas as pd

from trading import filings

NEW_LAYOUT = """<xbrli:xbrl>
<xbrli:context id="OneD"><xbrli:entity/><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FourD"><xbrli:entity/><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="OneI"><xbrli:entity/><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="Seg01D"><xbrli:entity/><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="x">y</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-5">1000</in-capmkt:RevenueFromOperations>
<in-capmkt:RevenueFromOperations contextRef="FourD" unitRef="INR" decimals="-5">3800</in-capmkt:RevenueFromOperations>
<in-capmkt:RevenueFromOperations contextRef="Seg01D" unitRef="INR" decimals="-5">400</in-capmkt:RevenueFromOperations>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" unitRef="INR" decimals="-5">0</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="-5">100</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitLossForPeriod contextRef="FourD" unitRef="INR" decimals="-5">380</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitBeforeTax contextRef="FourD" unitRef="INR" decimals="-5">500</in-capmkt:ProfitBeforeTax>
<in-capmkt:FinanceCosts contextRef="FourD" unitRef="INR" decimals="-5">40</in-capmkt:FinanceCosts>
<in-capmkt:CashFlowsFromUsedInOperatingActivities contextRef="FourD" unitRef="INR" decimals="-5">420</in-capmkt:CashFlowsFromUsedInOperatingActivities>
<in-capmkt:EquityAttributableToOwnersOfParent contextRef="OneI" unitRef="INR" decimals="-5">2000</in-capmkt:EquityAttributableToOwnersOfParent>
<in-capmkt:BorrowingsCurrent contextRef="OneI" unitRef="INR" decimals="-5">100</in-capmkt:BorrowingsCurrent>
<in-capmkt:BorrowingsNoncurrent contextRef="OneI" unitRef="INR" decimals="-5">300</in-capmkt:BorrowingsNoncurrent>
<in-capmkt:EquityShareCapital contextRef="OneI" unitRef="INR" decimals="-5">50</in-capmkt:EquityShareCapital>
<in-capmkt:FaceValueOfEquityShareCapital contextRef="OneD" unitRef="INRPerShare" decimals="2">5</in-capmkt:FaceValueOfEquityShareCapital>
</xbrli:xbrl>"""

# Older filings use OneD/FourD without defining them; dates come from facts.
OLD_LAYOUT = """<xbrli:xbrl>
<in-bse-fin:DateOfStartOfReportingPeriod contextRef="OneD">2018-07-01</in-bse-fin:DateOfStartOfReportingPeriod>
<in-bse-fin:DateOfEndOfReportingPeriod contextRef="OneD">2018-09-30</in-bse-fin:DateOfEndOfReportingPeriod>
<in-bse-fin:DateOfStartOfReportingPeriod contextRef="FourD">2018-04-01</in-bse-fin:DateOfStartOfReportingPeriod>
<in-bse-fin:DateOfEndOfReportingPeriod contextRef="FourD">2018-09-30</in-bse-fin:DateOfEndOfReportingPeriod>
<in-bse-fin:NatureOfReportStandaloneConsolidated contextRef="OneD">Standalone</in-bse-fin:NatureOfReportStandaloneConsolidated>
<in-bse-fin:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-7">500</in-bse-fin:RevenueFromOperations>
<in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="-7">50</in-bse-fin:ProfitLossForPeriod>
<in-bse-fin:RevenueFromOperations contextRef="FourD" unitRef="INR" decimals="-7">950</in-bse-fin:RevenueFromOperations>
<in-bse-fin:ProfitLossForPeriod contextRef="FourD" unitRef="INR" decimals="-7">90</in-bse-fin:ProfitLossForPeriod>
</xbrli:xbrl>"""


def _by_months(rows):
    return {row["months"]: row for row in rows}


def test_new_layout_gives_quarter_year_balance_sheet_and_cash_flow():
    rows = _by_months(filings.parse_xbrl(NEW_LAYOUT))
    quarter, year = rows[3], rows[12]
    assert quarter["revenue"] == 1000 and quarter["net_income"] == 100   # 0 line skipped
    assert year["revenue"] == 3800 and year["cfo"] == 420 and year["pbt"] == 500
    assert year["equity"] == 2000 and year["borrowings"] == 400
    assert year["shares"] == 10 and year["consolidated"]


def test_segment_breakdowns_are_ignored():
    rows = filings.parse_xbrl(NEW_LAYOUT)
    assert len(rows) == 2


def test_old_layout_uses_the_reporting_period_dates():
    rows = _by_months(filings.parse_xbrl(OLD_LAYOUT))
    assert rows[3]["period_end"] == pd.Timestamp("2018-09-30") and rows[3]["revenue"] == 500
    assert rows[6]["period_start"] == pd.Timestamp("2018-04-01") and rows[6]["net_income"] == 90
    assert not rows[3]["consolidated"]


def test_one_filing_per_period_prefers_consolidated_and_the_original():
    listing = pd.DataFrame({
        "period_end": pd.to_datetime(["2024-06-30", "2024-06-30", "2024-06-30", "2019-06-30"]),
        "consolidated": [False, True, True, True],
        "filed": pd.to_datetime(["2024-07-20", "2024-07-20", "2024-09-01", "2019-07-20"]),
        "bank": False, "xbrl": ["standalone", "original", "revised", "old-june"]})
    wanted = filings.wanted_filings(listing)
    # June 2019 is before every-quarter downloads start; only March and September then
    assert wanted["xbrl"].tolist() == ["original"]


def test_nse_rows_win_and_yahoo_fills_missing_years_and_balance_sheet():
    nse = pd.DataFrame({"symbol": ["A", "A"],
                        "period_end": pd.to_datetime(["2025-03-31", "2026-03-31"]),
                        "revenue": [10.0, 12.0], "equity": [None, 50.0]})
    yahoo = pd.DataFrame({"symbol": ["A", "A", "A"],
                          "period_end": pd.to_datetime(["2024-03-31", "2025-03-31",
                                                        "2026-03-31"]),
                          "revenue": [8.0, 9.9, 11.9], "equity": [30.0, 40.0, 49.0]})
    merged = filings.merge_with_yahoo(nse, yahoo, ["symbol", "period_end", "revenue", "equity"],
                                      fill=["equity"])
    assert merged["revenue"].tolist() == [8.0, 10.0, 12.0]
    assert merged["equity"].tolist() == [30.0, 40.0, 50.0]
