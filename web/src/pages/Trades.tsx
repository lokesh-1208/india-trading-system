// Trades: record what you really bought and sold, and see your profit after charges.
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { postJson, Trades, useApi } from "../api";
import { useApp } from "../App";
import { Empty, Loading, Panel, Problem } from "../components/ui";
import { clock, useLive } from "../components/live";
import { day, pct, price, rupees, signedRupees } from "../format";

const todayText = () => new Date().toISOString().slice(0, 10);

export default function TradesPage() {
  const { version } = useApp();
  const { data, error, reload, setData } = useApi<Trades>("/api/trades", version);
  const [buy, setBuy] = useState({ symbol: "", date: todayText(), price: "", quantity: "", note: "" });
  const [sell, setSell] = useState({ row: "", date: todayText(), price: "" });
  const [message, setMessage] = useState<{ tone: string; text: string } | null>(null);
  // A delete or undo asks once more on the same button before it happens.
  const [confirming, setConfirming] = useState<string | null>(null);
  const openSymbols = data ? Array.from(new Set(data.open.map((row) => row.symbol))).sort() : [];
  const { live } = useLive(openSymbols);

  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading count={3} height={120} />;
  const totals = data.totals;
  // With live prices, value and gain are for now; without them, at the last close.
  const nowPrice = (symbol: string, last: number) => live?.prices[symbol]?.price ?? last;
  const liveValue = data.open.reduce((sum, row) => sum + nowPrice(row.symbol, row.last_price) * row.quantity, 0);
  const isLive = !!live && data.open.some((row) => live.prices[row.symbol]);
  const value = isLive ? liveValue : totals.value;
  const openGain = isLive ? liveValue - totals.invested : totals.open_gain;

  const submitBuy = (event: FormEvent) => {
    event.preventDefault();
    postJson<Trades>("/api/trades/buy", { ...buy, price: Number(buy.price), quantity: Number(buy.quantity) })
      .then((found) => { setData(found); setMessage({ tone: "up", text: `Saved: bought ${buy.quantity} ${buy.symbol.toUpperCase()}.` });
        setBuy({ ...buy, symbol: "", price: "", quantity: "", note: "" }); })
      .catch((problem: Error) => setMessage({ tone: "down", text: problem.message }));
  };
  const submitSell = (event: FormEvent) => {
    event.preventDefault();
    postJson<Trades>("/api/trades/sell", { row: Number(sell.row), date: sell.date, price: Number(sell.price) })
      .then((found) => { setData(found); setMessage({ tone: "up", text: "Saved the sale." }); setSell({ ...sell, row: "", price: "" }); })
      .catch((problem: Error) => setMessage({ tone: "down", text: problem.message }));
  };

  const fixMistake = (kind: "delete" | "undo-sell", row: number, done: string) => {
    const key = `${kind}-${row}`;
    if (confirming !== key) { setConfirming(key); return; }
    setConfirming(null);
    postJson<Trades>(`/api/trades/${kind}`, { row })
      .then((found) => { setData(found); setMessage({ tone: "up", text: done }); })
      .catch((problem: Error) => setMessage({ tone: "down", text: problem.message }));
  };
  const fixButton = (kind: "delete" | "undo-sell", row: number, label: string, done: string) => {
    const asking = confirming === `${kind}-${row}`;
    return (
      <td className="right">
        <button type="button" className={`small${asking ? " danger" : ""}`} onClick={() => fixMistake(kind, row, done)}
          onBlur={() => asking && setConfirming(null)} title={asking ? "Click again to confirm" : label}>
          {asking ? "Sure?" : label}
        </button>
      </td>
    );
  };

  return (
    <>
      <h1>Your trades</h1>
      <p className="small muted" style={{ marginTop: -8 }}>Look up any stock with "Find a stock" at the top.</p>
      <div className="grid-tiles">
        <div className="tile"><span className="name">Money in the market</span><span className="value num">{rupees(totals.invested)}</span></div>
        <div className="tile"><span className="name">{isLive ? "Worth now (live)" : "Worth at the last close"}</span>
          <span className="value num" data-testid="worth">{rupees(value)}</span>
          {isLive ? <span className="note">{rupees(totals.value)} at the last close · {clock(live?.time)}</span> : null}</div>
        <div className="tile"><span className="name">{isLive ? "Gain now (live)" : "Gain on open positions"}</span>
          <span className={`value num ${openGain >= 0 ? "up" : "down"}`} data-testid="open-gain">{signedRupees(openGain)}</span></div>
        <div className="tile"><span className="name">Closed trades, after charges</span>
          <span className={`value num ${totals.closed_net >= 0 ? "up" : "down"}`}>{signedRupees(totals.closed_net)}</span>
          <span className="note">{totals.tax_estimate ? `tax about ${rupees(totals.tax_estimate)}` : `${totals.closed_count} closed`}</span></div>
      </div>

      <section className="panel record" aria-label="Record a trade">
        <div className="section-head">
          <h3>Record a trade</h3>
          <span className="small muted">Enter the exact price Zerodha filled at. Saved in journal/real_trades.csv on this computer only.</span>
        </div>
        <form className="record-row" onSubmit={submitBuy} aria-label="Record a buy">
          <span className="side-tag buy">Buy</span>
          <label className="grow">Stock
            <input list="symbols" required value={buy.symbol} placeholder="Symbol"
              onChange={(event) => setBuy({ ...buy, symbol: event.target.value })} />
          </label>
          <datalist id="symbols">{data.symbols.map((symbol) => <option key={symbol} value={symbol} />)}</datalist>
          <label>Date<input type="date" required value={buy.date} onChange={(event) => setBuy({ ...buy, date: event.target.value })} /></label>
          <label>Price (₹)<input type="number" step="any" min="0.01" inputMode="decimal" required value={buy.price}
            onChange={(event) => setBuy({ ...buy, price: event.target.value })} /></label>
          <label>Quantity<input type="number" step="1" min="1" inputMode="numeric" required value={buy.quantity}
            onChange={(event) => setBuy({ ...buy, quantity: event.target.value })} /></label>
          <label className="grow">Note<input value={buy.note} placeholder="optional"
            onChange={(event) => setBuy({ ...buy, note: event.target.value })} /></label>
          <button className="primary" type="submit">Save buy</button>
        </form>
        {data.open.length === 0 ? (
          <div className="record-row"><span className="side-tag sell">Sell</span><span className="small muted">Nothing open to sell.</span></div>
        ) : (
          <form className="record-row" onSubmit={submitSell} aria-label="Record a sell">
            <span className="side-tag sell">Sell</span>
            <label className="grow">Position
              <select required value={sell.row} onChange={(event) => {
                const chosen = data.open.find((row) => String(row.row) === event.target.value);
                const now = chosen ? live?.prices[chosen.symbol]?.price : undefined;
                setSell({ ...sell, row: event.target.value, price: sell.price || (now ? String(now) : "") });
              }}>
                <option value="">Choose…</option>
                {data.open.map((row) => (
                  <option key={row.row} value={row.row}>{row.symbol}: {row.quantity} at {price(row.buy_price)} ({day(row.buy_date)})</option>
                ))}
              </select>
            </label>
            <label>Date<input type="date" required value={sell.date} onChange={(event) => setSell({ ...sell, date: event.target.value })} /></label>
            <label>Price (₹)<input type="number" step="any" min="0.01" inputMode="decimal" required value={sell.price}
              onChange={(event) => setSell({ ...sell, price: event.target.value })} /></label>
            <button className="danger-solid" type="submit">Save sell</button>
          </form>
        )}
        {message ? <div className={`notice ${message.tone}`} role="status">{message.text}</div> : null}
      </section>

      <div className="stack">
          <Panel title="Open positions">
            {data.open.length === 0 ? <Empty>No open positions recorded.</Empty> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Stock</th><th>Bought</th><th className="right">Price</th><th className="right">Qty</th>
                    <th className="right">{isLive ? "Live" : "Last close"}</th><th className="right">Gain</th><th></th></tr></thead>
                  <tbody>
                    {data.open.map((row) => (
                      <tr key={row.row}>
                        <td><Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link></td>
                        <td className="small">{day(row.buy_date)}</td>
                        <td className="right num">{price(row.buy_price)}</td>
                        <td className="right num">{row.quantity}</td>
                        <td className="right num">{price(nowPrice(row.symbol, row.last_price))}</td>
                        {(() => {
                          const gain = (nowPrice(row.symbol, row.last_price) - row.buy_price) * row.quantity;
                          const gainPct = (nowPrice(row.symbol, row.last_price) / row.buy_price - 1) * 100;
                          return <td className={`right num ${gain >= 0 ? "up" : "down"}`}>{signedRupees(gain)} ({pct(gainPct)})</td>;
                        })()}
                        {fixButton("delete", row.row, "Delete", `Deleted the ${row.symbol} buy.`)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <Panel title="Closed trades">
            {data.closed.length === 0 ? <Empty>No closed trades yet.</Empty> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Stock</th><th>Bought</th><th>Sold</th><th className="right">Profit</th>
                    <th className="right">Charges</th><th className="right">After charges</th><th></th></tr></thead>
                  <tbody>
                    {data.closed.map((row) => (
                      <tr key={row.row}>
                        <td style={{ fontWeight: 600 }}>{row.symbol}</td>
                        <td className="small">{day(row.buy_date)} at {price(row.buy_price)}</td>
                        <td className="small">{day(row.sell_date)} at {price(row.sell_price)}</td>
                        <td className={`right num ${row.profit >= 0 ? "up" : "down"}`}>{signedRupees(row.profit)} ({pct(row["profit_%"])})</td>
                        <td className="right num muted">{rupees(row.charges, 2)}</td>
                        <td className={`right num ${row.net_profit >= 0 ? "up" : "down"}`}>{signedRupees(row.net_profit)}</td>
                        {fixButton("undo-sell", row.row, "Undo sell", `Undid the ${row.symbol} sale; it is open again.`)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        <p className="small muted">Entered something by mistake? "Delete" removes an open buy; "Undo sell" reopens a sold position. Both ask once more before saving.</p>
      </div>
    </>
  );
}
