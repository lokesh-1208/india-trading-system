"""Checks the reading of NSE shareholding filings (new and old file formats)."""

import pandas as pd

from trading import shareholding

TAG = "ShareholdingAsAPercentageOfTotalNumberOfShares"


def _fact(context, value, tag=TAG):
    return f'<in-bse-shp:{tag} contextRef="{context}" unitRef="pure">{value}</in-bse-shp:{tag}>'


NEW_FORMAT = "".join([
    _fact("ShareholdingOfPromoterAndPromoterGroup_ContextI", "0.5048"),
    _fact("MutualFundsOrUTI_ContextI", "0.1011"),
    _fact("InsuranceCompanies_ContextI", "0.092"),
    _fact("InstitutionsDomestic_ContextI", "0.2119"),
    _fact("InstitutionsForeign_ContextI", "0.172"),
    _fact("ShareholdingPattern_ContextI", "1"),
    _fact("MutualFundsOrUTI_Context15", "0.0262"),
    _fact("MutualFundsOrUTI_Context16", "0.0176"),
    _fact("InsuranceCompanies_Context15", "0.06"),
    _fact("D_MutualFundsOrUTI_Context15", "SBI Mutual Funds", "NameOfTheShareholder"),
    _fact("D_MutualFundsOrUTI_Context16", "ICICI Prudential Mutual Funds", "NameOfTheShareholder"),
    _fact("D_InsuranceCompanies_Context15", "Life Insurance Corporation", "NameOfTheShareholder"),
    "<in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged "
    'contextRef="MainI">false</in-bse-shp:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged>',
])

OLD_FORMAT = "".join([
    _fact("ShareholdingOfPromoterAndPromoterGroupI", "50.27"),
    _fact("MutualFundsOrUtiI", "6.56"),
    _fact("InsuranceCompaniesI", "8.41"),
    _fact("InstitutionsDomesticI", "16.07"),
    _fact("InstitutionsForeignI", "22.6"),
    _fact("ShareholdingPatternI", "100"),
    _fact("DetailsOfSharesHeldByMutualFundsOrUti001I", "2.11"),
    _fact("DetailsOfSharesHeldByMutualFundsOrUti001D", "SBI Mutual Funds", "NameOfTheShareholder"),
    "<in-bse-shp:WhetherAnySharesHeldByPromotersArePledgeOrOtherwiseEncumbered "
    'contextRef="MainI">Yes</in-bse-shp:WhetherAnySharesHeldByPromotersArePledgeOrOtherwiseEncumbered>',
])


def test_new_format_is_read_and_turned_into_percent():
    holdings, funds = shareholding.parse_filing(NEW_FORMAT)
    assert holdings["promoter"] == 50.48
    assert holdings["fii"] == 17.2
    assert holdings["dii"] == 21.19
    assert holdings["mutual_funds"] == 10.11
    assert holdings["insurance"] == 9.2
    assert holdings["public"] == 11.13          # 100 - 50.48 - 17.2 - 21.19
    assert holdings["promoters_pledged"] is False
    # only mutual funds are listed, largest first; the insurer is left out
    assert funds == [("SBI Mutual Funds", 2.62), ("ICICI Prudential Mutual Funds", 1.76)]


def test_old_format_is_read_the_same_way():
    holdings, funds = shareholding.parse_filing(OLD_FORMAT)
    assert holdings["promoter"] == 50.27
    assert holdings["fii"] == 22.6
    assert holdings["dii"] == 16.07
    assert holdings["mutual_funds"] == 6.56
    assert holdings["public"] == 11.06
    assert holdings["promoters_pledged"] is True
    assert funds == [("SBI Mutual Funds", 2.11)]


def test_a_file_that_is_not_a_shareholding_filing_gives_nothing():
    assert shareholding.parse_filing("<html>Access denied</html>") == (None, [])


def test_summary_shows_the_change_from_the_previous_quarter():
    rows = pd.DataFrame({
        "symbol": "T",
        "quarter_end": pd.to_datetime(["2026-03-31", "2026-06-30"]),
        "promoter": [50.0, 50.0], "fii": [20.0, 18.5], "dii": [15.0, 16.25],
        "mutual_funds": [8.0, 9.0], "insurance": [5.0, 5.0], "public": [15.0, 15.25],
        "promoters_pledged": [False, False],
    })
    funds = pd.DataFrame({
        "symbol": "T",
        "quarter_end": pd.to_datetime(["2026-03-31", "2026-06-30", "2026-06-30"]),
        "fund": ["Old Fund", "Small Fund", "Big Fund"],
        "percent": [1.5, 1.1, 2.4],
    })
    result = shareholding.summary(rows, funds)
    assert result["fii"] == 18.5 and result["fii_change"] == -1.5
    assert result["dii_change"] == 1.25 and result["mutual_funds_change"] == 1.0
    assert result["promoters_pledged"] is False
    # only the latest quarter's funds, largest first
    assert result["funds"] == [("Big Fund", 2.4), ("Small Fund", 1.1)]


def test_summary_with_one_quarter_has_no_change_figures():
    rows = pd.DataFrame({
        "symbol": "T", "quarter_end": pd.to_datetime(["2026-06-30"]),
        "promoter": [50.0], "fii": [18.5], "dii": [16.25], "mutual_funds": [9.0],
        "insurance": [5.0], "public": [15.25], "promoters_pledged": [True],
    })
    result = shareholding.summary(rows)
    assert result["fii_change"] is None and result["promoters_pledged"] is True
    assert result["funds"] == []


def test_no_shareholding_data_gives_none():
    assert shareholding.summary(None) is None


def test_only_quarter_end_filings_are_kept():
    assert shareholding.is_quarter_end(pd.Timestamp("2026-06-30"))
    assert shareholding.is_quarter_end(pd.Timestamp("2025-12-31"))
    assert not shareholding.is_quarter_end(pd.Timestamp("2024-10-29"))   # filed after a bonus issue
    assert not shareholding.is_quarter_end(pd.Timestamp("2026-07-31"))   # month end, not a quarter end


OLDEST_FORMAT = "".join([
    _fact("ShareholdingOfPromoterAndPromoterGroupI", "50.61"),
    _fact("MutualFundsOrUtiI", "4.6"),
    _fact("InsuranceCompaniesI", "6.22"),
    _fact("ForeignVentureCapitalInvestorsI", "0"),
    _fact("InstitutionsForeignPortfolioInvestorI", "25.39"),
    _fact("InstitutionsI", "38.61"),
    _fact("ShareholdingPatternI", "100"),
])


def test_oldest_format_splits_institutions_into_foreign_and_indian():
    holdings, funds = shareholding.parse_filing(OLDEST_FORMAT)
    assert holdings["promoter"] == 50.61
    assert holdings["fii"] == 25.39
    assert holdings["dii"] == 13.22            # 38.61 institutions - 25.39 foreign
    assert holdings["mutual_funds"] == 4.6
    assert holdings["public"] == 10.78         # 100 - 50.61 - 25.39 - 13.22
