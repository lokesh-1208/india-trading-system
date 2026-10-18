"""Checks the FII/DII and large-deal collector."""

import pandas as pd

from trading import flows

FII_DII = [
    {"category": "DII **", "date": "09-Oct-2026", "buyValue": "15,000.50",
     "sellValue": "10257.24", "netValue": "4743.26"},
    {"category": "FII/FPI *", "date": "09-Oct-2026", "buyValue": "9000",
     "sellValue": "12568.9", "netValue": "-3568.9"},
]
DEALS = {
    "BULK_DEALS_DATA": [
        {"date": "09-Oct-2026", "symbol": "TCS", "name": "Tata Consultancy", "clientName": "BIG  FUND",
         "buySell": "BUY", "qty": "2000000", "watp": "3500.5"},
        {"date": "09-Oct-2026", "symbol": "", "name": "No symbol", "clientName": "X",
         "buySell": "SELL", "qty": "1", "watp": "1"},
    ],
    "BLOCK_DEALS_DATA": [
        {"date": "09-Oct-2026", "symbol": "INFY", "name": "Infosys", "clientName": "SELLER LTD",
         "buySell": "SELL", "qty": "1000000", "watp": "1500"},
    ],
}


def test_fii_dii_rows():
    table = flows.flow_rows(FII_DII)
    assert list(table["who"]) == ["DII", "FII"]
    assert table.loc[0, "bought"] == 15000.50              # the comma is handled
    assert table.loc[1, "net"] == -3568.9
    assert table.loc[0, "date"] == pd.Timestamp("2026-10-09")
    assert len(flows.flow_rows({"error": "blocked"})) == 0


def test_deal_rows():
    table = flows.deal_rows(DEALS)
    assert list(table["symbol"]) == ["TCS", "INFY"]        # the row without a symbol is left out
    assert list(table["kind"]) == ["Bulk", "Block"]
    assert list(table["side"]) == ["Buy", "Sell"]
    assert table.loc[0, "client"] == "BIG FUND"
    assert len(flows.deal_rows(None)) == 0


def test_the_same_day_twice_is_stored_once():
    table = flows.flow_rows(FII_DII)
    merged = flows.merge(table, table, ["date", "who"])
    assert len(merged) == 2
    next_day = table.assign(date=pd.Timestamp("2026-10-12"))
    assert len(flows.merge(merged, next_day, ["date", "who"])) == 4


def test_daily_net_has_one_row_per_day():
    net = flows.daily_net(flows.flow_rows(FII_DII))
    assert net.loc[pd.Timestamp("2026-10-09"), "FII"] == -3568.9
    assert net.loc[pd.Timestamp("2026-10-09"), "DII"] == 4743.26
    assert len(flows.daily_net(flows.flow_rows([]))) == 0


def test_update_adds_only_new_rows(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "FII_DII_FILE", tmp_path / "flows" / "f.csv")
    monkeypatch.setattr(config, "LARGE_DEALS_FILE", tmp_path / "flows" / "d.csv")
    monkeypatch.setattr(flows.nse, "session", lambda: None)
    monkeypatch.setattr(flows.nse, "get_json",
                        lambda browser, path, **params: FII_DII if "fiidii" in path else DEALS)
    assert flows.update() == (1, 2)
    assert flows.update() == (1, 0)
    assert len(flows.load_flows()) == 2 and len(flows.load_deals()) == 2
