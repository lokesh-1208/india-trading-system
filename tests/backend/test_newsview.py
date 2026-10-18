"""Checks the news reading: good or bad, results numbers, past reactions and ideas."""

import pandas as pd

from trading import newsview

DAYS = pd.bdate_range("2026-09-01", "2026-10-13")


def test_rules_read_common_announcements():
    assert newsview.read("Orders and contracts", "Bagging of a large order")[0] == 1
    assert newsview.read("Credit rating", "CRISIL upgraded the rating to AA+")[0] == 1
    assert newsview.read("Credit rating", "Rating downgraded to BBB")[0] == -1
    assert newsview.read("Legal and regulatory", "Fraud/Default/Arrest")[0] == -2
    assert newsview.read("Management change", "Resignation of the Chief Financial Officer")[0] == -1
    assert newsview.read("Management change", "Resignation of statutory auditor")[1] == "Auditor quit"
    assert newsview.read("Raising money", "Qualified Institutional Placement")[0] == -1
    assert newsview.read("Raising money", "Buy back of shares")[0] == 1


def test_results_compare_with_the_same_quarter_a_year_ago():
    quarterly = pd.DataFrame({"symbol": ["A", "A"],
                              "period_end": pd.to_datetime(["2025-09-30", "2026-09-30"]),
                              "revenue": [100.0, 120.0], "net_income": [10.0, 14.0]})
    lean, label = newsview.results_lean("A", pd.Timestamp("2026-10-10"), quarterly)
    assert lean == 2 and label == "Results: profit +40% on a year ago, sales +20%"


def test_results_turning_into_a_loss_is_clearly_bad():
    quarterly = pd.DataFrame({"symbol": ["A", "A"],
                              "period_end": pd.to_datetime(["2025-09-30", "2026-09-30"]),
                              "revenue": [100.0, 90.0], "net_income": [10.0, -2.0]})
    assert newsview.results_lean("A", pd.Timestamp("2026-10-10"), quarterly)[0] == -2


def test_results_without_numbers_yet_are_neutral():
    assert newsview.results_lean("A", pd.Timestamp("2026-10-10"), None)[0] == 0


def test_news_after_the_close_counts_from_that_close():
    calendar = DAYS
    assert newsview.base_day(pd.Timestamp("2026-10-12 18:00"), calendar) == pd.Timestamp("2026-10-12")
    assert newsview.base_day(pd.Timestamp("2026-10-12 11:00"), calendar) == pd.Timestamp("2026-10-09")


def _reading(rows):
    return pd.DataFrame(rows, columns=["time", "symbol", "kind", "lean", "group", "label",
                                       "what", "link"])


def test_past_reaction_is_the_move_against_nifty():
    closes = pd.DataFrame({"A": 100.0}, index=DAYS)
    closes.loc["2026-09-10":, "A"] = 110.0                  # +10% the day after the news
    nifty = pd.Series(100.0, index=DAYS)
    reading = _reading([(pd.Timestamp("2026-09-09 18:00"), "A", "Orders and contracts", 1,
                         "Order or contract win", "Order or contract win", "", "")])
    reactions = newsview.past_reactions(reading, closes, nifty, days=3)
    assert reactions.iloc[0]["average_%"] == 10.0 and reactions.iloc[0]["cases"] == 1


def test_enough_past_cases_overrule_the_rule():
    reactions = pd.DataFrame({"group": ["Order or contract win"], "lean": [1], "cases": [500],
                              "average_%": [0.1], "beat_nifty_%": [49.0]})
    assert newsview.learned_lean("Order or contract win", 1, reactions) == 0
    few = reactions.assign(cases=5)
    assert newsview.learned_lean("Order or contract win", 1, few) == 1


def test_ideas_split_into_buys_and_exits_with_the_model_view():
    closes = pd.DataFrame({"GOOD": 100.0, "BAD": 100.0, "MINE": 100.0}, index=DAYS)
    reading = _reading([
        (pd.Timestamp("2026-10-12 18:00"), "GOOD", "Credit rating", 1, "Credit rating upgraded",
         "Credit rating upgraded", "upgraded", "l1"),
        (pd.Timestamp("2026-10-12 18:00"), "BAD", "Legal and regulatory", -2,
         "Fraud, default or insolvency", "Fraud, default or insolvency", "fraud", "l2"),
        (pd.Timestamp("2026-10-12 18:00"), "MINE", "Management change", -1,
         "Top manager (MD, CEO or CFO) quit", "Top manager (MD, CEO or CFO) quit", "CEO", ""),
    ])
    ranking = pd.DataFrame({"score": [70.0, 30.0, 65.0]}, index=["GOOD", "BAD", "MINE"])
    in_trend = {"GOOD": True, "BAD": False, "MINE": True}
    trend = pd.Series({"GOOD": 95.0, "BAD": 105.0, "MINE": 95.0})
    buys, exits = newsview.ideas(reading, ranking, in_trend, closes, trend, held={"MINE"},
                                 last_day=DAYS[-1])
    assert buys["symbol"].tolist() == ["GOOD"] and buys.iloc[0]["agree"] == "yes"
    assert set(exits["symbol"]) == {"BAD", "MINE"}
    assert exits.set_index("symbol").loc["MINE", "idea"].startswith("You hold it")


def test_filing_pdfs_soften_routine_fraud_and_supplier_insolvency_filings():
    # 12 Oct 2026, Bank of India: a borrower's NPA account declared as fraud (routine for a bank)
    bank = "Fraud/Default/Arrest NPA as detailed below has been declared as fraud. Reported to RBI"
    assert newsview.read("Legal and regulatory", bank) == (0, "Bank reported a borrower's fraud (routine)")
    # 8 Oct 2026, Polycab: a supplier's Rs 2.79 crore claim admitted by NCLT
    supplier = ("Corporate Insolvency Resolution Process Asier Metals ('Operational Creditor') "
                "vs Polycab India Limited ('Corporate Debtor')")
    assert newsview.read("Legal and regulatory", supplier)[0] == -1
    # Without the PDF the title alone still reads as clearly bad
    assert newsview.read("Legal and regulatory", "Corporate Insolvency Resolution Process")[0] == -2
