// Intraday (experimental): the 9:30 scan, trade cards, your day's limits, Zerodha, and your journal.
// Kept apart from the swing model. Orders are placed by you in Kite; nothing here buys or sells.
import { FormEvent, Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  EvidenceSet, Guard, IntradayCandidate, JournalPage, postJson, ScanState, useApi, ZStatus,
} from "../api";
import { Empty, Loading, Panel, Problem, Tag } from "../components/ui";
import { ZerodhaAccount } from "../components/Zerodha";
import { price, rupees, share, signedRupees } from "../format";

type Prefill = { symbol: string; side: string; qty: string; entry: string; stop: string; target: string; rule: string; key: number };

const tone = (value: number) => (value >= 0 ? "up" : "down");

// ---------------------------------------------------------------- the day's rules
function DayGuard({ guard }: { guard: Guard }) {
  const s = guard.settings;
  return (
    <>
      <div className="grid-tiles">
        <div className="tile"><span className="name">Market clock ({guard.time})</span>
          <span className="value" style={{ fontSize: 15 }}>{guard.phase.label}</span></div>
        <div className="tile"><span className="name">Trades today</span>
          <span className="value num">{guard.trades_used} of {guard.trades_max}</span>
          <span className="note">{guard.open_trades} open now</span></div>
        <div className="tile"><span className="name">Closed profit today (after charges)</span>
          <span className={`value num ${tone(guard.realised_net)}`}>{signedRupees(guard.realised_net)}</span>
          <span className="note">stop for the day at −{rupees(guard.loss_limit)}</span></div>
        <div className="tile"><span className="name">New entries</span>
          <span className={`value ${guard.entries_allowed ? "up" : "down"}`}>{guard.entries_allowed ? "Allowed" : "Blocked"}</span>
          <span className="note">{guard.blockers[0] ?? "inside your limits"}</span></div>
      </div>
      <p className="small muted">
        Your rules: {rupees(s.capital)} capital, about {rupees(s.risk_per_trade)} risked per trade, target {s.target_r}× the stop,
        no entries after {s.last_entry}, square off by {s.square_off}. Quantity comes from the stop distance, so a stop-out costs about {rupees(s.risk_per_trade)} plus charges.
      </p>
    </>
  );
}

// ---------------------------------------------------------------- Zerodha (setup lives in Settings)
function ZerodhaSummary() {
  const status = useApi<ZStatus>("/api/zerodha/status");
  if (status.error) return <Problem error={status.error} retry={status.reload} />;
  if (!status.data) return <Loading height={60} />;
  return (
    <Panel title="Zerodha" aside={<Link to="/settings">Zerodha settings</Link>}>
      {status.data.connected ? <ZerodhaAccount /> : (
        <div className="notice warn">
          {status.data.configured ? "Not logged in to Zerodha today." : "Zerodha is not set up yet."}{" "}
          <Link to="/settings">{status.data.configured ? "Connect in Settings" : "Set it up in Settings"}</Link>.
          Kasauti works without it, but your funds, positions and orders will not show here.
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- scan and trade cards
// Both directions for one stock, with every exit price known before you enter.
function SidePlans({ c }: { c: IntradayCandidate }) {
  const rows = (["BUY", "SELL"] as const).map((name) => {
    const p = c.plans?.[name];
    return p ? { name, p } : null;
  }).filter((r): r is NonNullable<typeof r> => r !== null);
  if (!rows.length) return null;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Side</th><th>Enter when</th><th className="right">Entry</th><th className="right">SL-M trigger</th>
          <th className="right">SL trigger / limit</th><th className="right">Target</th><th className="right">Trail: at → stop to</th>
          <th className="right">Qty</th><th className="right">Net if target / stop</th></tr></thead>
        <tbody>{rows.map(({ name, p }) => {
          const l = p.levels;
          const buy = name === "BUY";
          const when = buy ? `candle closes above ${price(c.or_high)} and VWAP` : `candle closes below ${price(c.or_low)} and VWAP`;
          return (
            <Fragment key={name}>
              <tr>
                <td><span className={buy ? "up" : "down"}>{buy ? "BUY (long)" : "SELL (short)"}</span>{" "}
                  <Tag tone={p.with_gap ? "up" : "warn"}>{p.with_gap ? "with the gap: tested" : "against the gap: untested"}</Tag></td>
                <td className="small">{when}</td>
                {l.skip ? <td colSpan={7} className="small muted">No plan: {l.skip}</td> : (
                  <>
                    <td className="right num">{price(l.entry)}</td><td className="right num down">{price(l.sl_m_trigger)}</td>
                    <td className="right num down">{price(l.sl_trigger)} / {price(l.sl_limit)}</td><td className="right num up">{price(l.target)}</td>
                    <td className="right num">{price(l.trail_at)} → {price(l.trail_to)}</td><td className="right num">{l.qty}</td>
                    <td className="right num">{signedRupees(l.net_if_target)} / {signedRupees(l.net_if_stop)}</td>
                  </>
                )}
              </tr>
            </Fragment>
          );
        })}</tbody>
      </table>
      <div className="small muted">Entry shown is the range edge plus slippage; your real entry is the next candle's open after the signal, and the card below updates the numbers then.
        Place the stop and the target together right after you are filled. Kite has no automatic trailing stop for shares, so you move the stop yourself when price touches the trail level.</div>
    </div>
  );
}

function Card({ c, onLog, canLog }: { c: IntradayCandidate; onLog: (c: IntradayCandidate) => void; canLog: boolean }) {
  const sg = c.signal;
  const buy = c.direction === "BUY";
  const trigger = buy
    ? `a 5-minute candle closes above ${price(c.or_high)} and above VWAP (${price(c.vwap)})`
    : `a 5-minute candle closes below ${price(c.or_low)} and below VWAP (${price(c.vwap)})`;
  return (
    <div className={`intraday-card ${buy ? "buy" : "sell"}`}>
      <div className="ic-head">
        <strong>{c.symbol}</strong>
        <Tag tone={buy ? "up" : "down"}>{c.direction} side</Tag>
        <Tag tone={TIER_TAG[c.tier][0]}>{TIER_TAG[c.tier][1]}</Tag>
        <span className="small muted">gap {share(c.gap_pct, 1, true)} · opening volume {c.rel_vol}× normal</span>
      </div>
      <div className="ic-facts">
        <span>Opening range {price(c.or_low)} – {price(c.or_high)} ({share(c.or_range_pct, 1)})</span>
        <span>Last {price(c.last)} (candle {c.last_candle})</span>
        <span>VWAP {price(c.vwap)}</span>
      </div>
      <SidePlans c={c} />
      {sg.state === "waiting" ? <div className="small">Waiting: no entry until {trigger}.</div> : null}
      {sg.state === "skipped" ? <div className="notice warn">Signal at {sg.signal_time} skipped: {sg.reason}.</div> : null}
      {sg.state === "stopped" ? <div className="notice down">Signal at {sg.signal_time} has already hit its stop. Do not enter.</div> : null}
      {sg.state === "target" ? <div className="notice warn">Signal at {sg.signal_time} has already reached its target. Do not chase.</div> : null}
      {sg.state === "live" || sg.state === "late" ? (
        <>
          {sg.state === "late" ? (
            <div className="notice warn">Signal was at {sg.signal_time}, {sg.age_candles} candles ago. Enter only if the price is still close to the entry below.</div>
          ) : <div className="small">Signal at {sg.signal_time}: {trigger.replace("a 5-minute candle closes", "a candle closed")}.</div>}
          <div className="ic-plan">
            <div><span className="name">Entry (about)</span><span className="value num">{price(sg.entry)}</span></div>
            <div><span className="name">Stop-loss (SL-M trigger)</span><span className="value num down">{price(sg.stop)}</span></div>
            <div><span className="name">Or SL: trigger / limit</span><span className="value num down">{price(sg.sl_trigger)} / {price(sg.sl_limit)}</span></div>
            <div><span className="name">Trail: at {price(sg.trail_at)} move stop to</span><span className="value num">{price(sg.trail_to)}</span></div>
            <div><span className="name">Target</span><span className="value num up">{price(sg.target)}</span></div>
            <div><span className="name">Quantity</span><span className="value num">{sg.qty}</span></div>
            <div><span className="name">Position value</span><span className="value num">{rupees(sg.value)}</span></div>
            <div><span className="name">Risk if stopped</span><span className="value num down">{rupees(sg.risk)}</span></div>
            <div><span className="name">Net if target</span><span className="value num up">{signedRupees(sg.net_if_target)}</span></div>
            <div><span className="name">Net if stopped</span><span className="value num down">{signedRupees(sg.net_if_stop)}</span></div>
          </div>
          <div className="ic-order">{sg.order}</div>
          <div><button className="primary" type="button" disabled={!canLog} onClick={() => onLog(c)}
            title={canLog ? "Copies these levels into the journal form below" : "Your day rules block new entries right now"}>
            I took this trade: add to journal</button></div>
        </>
      ) : null}
    </div>
  );
}

const STATE_TAG: Record<string, [string, string]> = {
  waiting: ["plain", "Waiting"], live: ["up", "Signal"], late: ["warn", "Late signal"],
  stopped: ["down", "Stopped"], target: ["warn", "Target hit"], skipped: ["warn", "Skipped"],
};
const TIER_TAG: Record<string, [string, string]> = {
  tested: ["blue", "Tested top 5"], in_play: ["plain", "In play"], near: ["warn", "Near miss"],
};

function ScanPanel({ guard, onLog }: { guard: Guard; onLog: (c: IntradayCandidate) => void }) {
  const state = useApi<ScanState>("/api/intraday/scan");
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "live" | "tested">("all");
  const [open, setOpen] = useState<string[]>([]);
  const running = state.data?.run.running;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => state.reload(), 2000);
    return () => clearInterval(timer);
  }, [running]);                                                      // eslint-disable-line react-hooks/exhaustive-deps

  const start = (full: boolean) => {
    setMessage(null);
    postJson<ScanState>("/api/intraday/scan", { full }).then(state.setData).catch((error: Error) => setMessage(error.message));
  };
  if (state.error) return <Problem error={state.error} retry={state.reload} />;
  if (!state.data) return <Loading height={120} />;
  const { run, result } = state.data;
  const progress = run.total ? Math.min(100, Math.round((run.done / run.total) * 100)) : 0;
  const all = result?.status === "ok" ? result.candidates : [];
  const isLive = (c: IntradayCandidate) => c.signal.state === "live" || c.signal.state === "late";
  const liveNow = all.filter(isLive);
  const shown = all.filter((c) => (filter === "live" ? isLive(c) : filter === "tested" ? c.tier === "tested" : true));
  const toggle = (symbol: string) => setOpen(open.includes(symbol) ? open.filter((x) => x !== symbol) : [...open, symbol]);

  return (
    <Panel title="Today's 20 stocks to watch" aside="Gapped on unusually high opening volume. Trade only in the direction of the gap. You choose which to trade.">
      <div className="record-row">
        <span className="small grow">Run the full scan after 9:30 (a few minutes). Then press "Refresh signals" every few minutes to update the same stocks.</span>
        <button className="primary" type="button" disabled={!!running} onClick={() => start(true)}>Run full scan</button>
        <button type="button" disabled={!!running || !all.length} onClick={() => start(false)}>Refresh signals</button>
      </div>
      {running ? (
        <div className="job" role="status"><span>{run.step}{run.total ? ` (${run.done}/${run.total})` : ""}</span>
          <div className="progress"><div style={{ width: `${progress}%` }} /></div></div>
      ) : null}
      {run.error ? <div className="notice down" role="alert">The scan failed: {run.error}</div> : null}
      {message ? <div className="notice down" role="alert">{message}</div> : null}

      {!result ? <Empty>No scan yet. Press "Run full scan" after 9:30.</Empty> : result.status !== "ok" ? (
        <div className="notice warn">{result.message}</div>
      ) : (
        <>
          <div className="small muted">
            Scanned {result.scanned} stocks · {result.in_play} in play · {result.near_miss} near misses · scan time {result.as_of.slice(11)}
            {result.is_today ? null : ` · showing the last session (${result.session_date}); the market is closed`}
            {result.no_history ? ` · ${result.no_history} stocks skipped (not enough saved history)` : ""}
          </div>
          <div className="notice warn">
            Only ranks 1–5 ("Tested top 5") match what the backtests used. The other in-play stocks use the same entry rules on a wider list and have not been tested.
            Near misses have a smaller gap or volume and are filled in only to reach 20. Your limit stays {guard.trades_max} trades a day.
          </div>
          {result.is_today && (result.data_lag_minutes ?? 0) > 7 ? (
            <div className="notice warn">The free price data is about {result.data_lag_minutes} minutes behind. Check the live price in Kite before you enter.</div>
          ) : null}
          {!guard.entries_allowed ? <div className="notice warn">Entries are blocked right now: {guard.blockers.join("; ")}.</div> : null}

          {liveNow.length ? (
            <div className="stack" style={{ gap: 12 }}>
              <h4 style={{ margin: "4px 0 0" }}>Signals to act on now ({liveNow.length})</h4>
              {liveNow.map((c) => <Card key={c.symbol} c={c} onLog={onLog} canLog={guard.entries_allowed} />)}
            </div>
          ) : <div className="small muted">No live signal right now. A stock gets a trade card when a 5-minute candle closes beyond its opening range.</div>}

          <div className="tabs" role="group" aria-label="Filter the list">
            {([["all", `All ${all.length}`], ["live", `Live signals ${liveNow.length}`], ["tested", "Tested top 5"]] as const).map(([key, label]) => (
              <button key={key} type="button" className={filter === key ? "on" : ""} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>
            ))}
          </div>
          {shown.length === 0 ? <Empty>Nothing matches this filter.</Empty> : (
            <div className="table-wrap"><table>
              <thead><tr><th className="right">#</th><th>Stock</th><th>Side</th><th>List</th><th className="right">Gap</th><th className="right">Volume</th><th className="right">Last</th><th>Now</th><th></th></tr></thead>
              <tbody>{shown.map((c) => {
                const [stateTone, stateText] = STATE_TAG[c.signal.state];
                const [tierTone, tierText] = TIER_TAG[c.tier];
                const expanded = open.includes(c.symbol);
                return (
                  <Fragment key={c.symbol}>
                    <tr>
                      <td className="right num">{c.rank}</td><td><strong>{c.symbol}</strong></td>
                      <td><span className={c.direction === "BUY" ? "up" : "down"}>{c.direction}</span></td>
                      <td><Tag tone={tierTone}>{tierText}</Tag></td>
                      <td className="right num">{share(c.gap_pct, 1, true)}</td><td className="right num">{c.rel_vol}×</td>
                      <td className="right num">{price(c.last)}</td><td><Tag tone={stateTone}>{stateText}</Tag></td>
                      <td className="right"><button type="button" className="small" aria-expanded={expanded} onClick={() => toggle(c.symbol)}>{expanded ? "Hide" : "Details"}</button></td>
                    </tr>
                    {expanded ? <tr><td colSpan={9}><Card c={c} onLog={onLog} canLog={guard.entries_allowed} /></td></tr> : null}
                  </Fragment>
                );
              })}</tbody>
            </table></div>
          )}
          {result.others.length ? (
            <div className="small muted">Also in play or near, below the top 20 (not shown): {result.others.length} more stocks.</div>
          ) : null}
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- journal
function Journal({ prefill, onChange }: { prefill: Prefill | null; onChange: () => void }) {
  const page = useApi<JournalPage>("/api/intraday/journal");
  const blank = { symbol: "", side: "BUY", qty: "", entry: "", stop: "", target: "", rule: "gap_go", note: "" };
  const [form, setForm] = useState(blank);
  const [exits, setExits] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: string; text: string } | null>(null);

  useEffect(() => {
    if (prefill) setForm({ ...blank, symbol: prefill.symbol, side: prefill.side, qty: prefill.qty, entry: prefill.entry,
      stop: prefill.stop, target: prefill.target, rule: prefill.rule, note: "" });
  }, [prefill?.key]);                                                 // eslint-disable-line react-hooks/exhaustive-deps

  const done = (found: JournalPage, text: string) => { page.setData(found); setMessage({ tone: "up", text }); onChange(); };
  const fail = (error: Error) => setMessage({ tone: "down", text: error.message });
  const save = (event: FormEvent) => {
    event.preventDefault();
    postJson<JournalPage>("/api/intraday/journal/open", { ...form, qty: Number(form.qty), entry: Number(form.entry),
      stop: Number(form.stop), target: form.target ? Number(form.target) : null })
      .then((found) => { done(found, `Saved: ${form.side} ${form.qty} ${form.symbol.toUpperCase()}.`); setForm(blank); }).catch(fail);
  };
  const close = (id: string) => postJson<JournalPage>("/api/intraday/journal/close", { id: Number(id), exit: Number(exits[id]) })
    .then((found) => { done(found, "Trade closed."); setExits({ ...exits, [id]: "" }); }).catch(fail);
  const remove = (id: string) => {
    if (confirming !== id) { setConfirming(id); return; }
    setConfirming(null);
    postJson<JournalPage>("/api/intraday/journal/delete", { id: Number(id) }).then((found) => done(found, "Trade removed.")).catch(fail);
  };

  if (page.error) return <Problem error={page.error} retry={page.reload} />;
  if (!page.data) return <Loading height={120} />;
  const d = page.data;
  const t = d.totals;
  return (
    <Panel title="Your intraday journal" aside="Saved in journal/intraday_trades.csv on this computer only. Profit is after intraday charges.">
      <form className="record-row" onSubmit={save} aria-label="Add an intraday trade">
        <label>Stock<input required value={form.symbol} placeholder="Symbol" onChange={(e) => setForm({ ...form, symbol: e.target.value })} /></label>
        <label>Side<select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
          <option>BUY</option><option>SELL</option></select></label>
        <label>Qty<input type="number" min="1" step="1" required value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} /></label>
        <label>Entry ₹<input type="number" step="any" min="0.05" required value={form.entry} onChange={(e) => setForm({ ...form, entry: e.target.value })} /></label>
        <label>Stop-loss ₹<input type="number" step="any" min="0.05" required value={form.stop} onChange={(e) => setForm({ ...form, stop: e.target.value })} /></label>
        <label>Target ₹<input type="number" step="any" min="0.05" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} /></label>
        <label>Rule<select value={form.rule} onChange={(e) => setForm({ ...form, rule: e.target.value })}>
          {Object.entries(d.rules).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label className="grow">Note<input value={form.note} placeholder="optional" onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
        <button className="primary" type="submit">Save trade</button>
      </form>
      {message ? <div className={`notice ${message.tone}`} role="status">{message.text}</div> : null}

      {d.open.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>Open trade</th><th>Side</th><th className="right">Qty</th><th className="right">Entry</th><th className="right">Stop</th><th className="right">Target</th><th>Close it</th><th></th></tr></thead>
          <tbody>{d.open.map((r) => (
            <tr key={r.id}><td><strong>{r.symbol}</strong> <span className="small muted">{r.entry_time}</span></td><td>{r.side}</td>
              <td className="right num">{r.qty}</td><td className="right num">{price(Number(r.entry))}</td>
              <td className="right num">{price(Number(r.stop))}</td><td className="right num">{r.target ? price(Number(r.target)) : "–"}</td>
              <td><span className="inline-form"><input type="number" step="any" min="0.05" placeholder="exit ₹" aria-label={`Exit price for ${r.symbol}`}
                value={exits[r.id] ?? ""} onChange={(e) => setExits({ ...exits, [r.id]: e.target.value })} />
                <button type="button" className="small primary" disabled={!exits[r.id]} onClick={() => close(r.id)}>Close</button></span></td>
              <td className="right"><button type="button" className={`small${confirming === r.id ? " danger" : ""}`} onClick={() => remove(r.id)}
                onBlur={() => setConfirming(null)}>{confirming === r.id ? "Sure?" : "Delete"}</button></td></tr>))}</tbody>
        </table></div>
      ) : null}

      <div className="grid-tiles">
        <div className="tile"><span className="name">Closed trades</span><span className="value num">{t.closed_count}</span><span className="note">{t.days} trading days</span></div>
        <div className="tile"><span className="name">Net after charges</span><span className={`value num ${tone(t.net)}`}>{signedRupees(t.net)}</span><span className="note">charges {rupees(t.charges)}</span></div>
        <div className="tile"><span className="name">Win rate</span><span className="value num">{t.win_rate === null ? "–" : share(t.win_rate, 0)}</span></div>
        <div className="tile"><span className="name">Best / worst day</span><span className="value num">{t.best_day === null ? "–" : `${signedRupees(t.best_day)} / ${signedRupees(t.worst_day)}`}</span></div>
      </div>
      {d.by_rule.length ? (
        <div className="small muted">By rule: {d.by_rule.map((r) => `${r.rule}: ${r.trades} trades, ${signedRupees(r.net)}`).join(" · ")}</div>
      ) : null}
      {d.closed.length ? (
        <details><summary className="small">Closed trades ({d.closed.length})</summary>
          <div className="table-wrap"><table>
            <thead><tr><th>Date</th><th>Stock</th><th>Side</th><th className="right">Qty</th><th className="right">Entry</th><th className="right">Exit</th><th className="right">Gross</th><th className="right">Charges</th><th className="right">Net</th><th>Rule</th></tr></thead>
            <tbody>{d.closed.map((r) => (
              <tr key={r.id}><td className="small">{r.date}</td><td><strong>{r.symbol}</strong></td><td>{r.side}</td><td className="right num">{r.qty}</td>
                <td className="right num">{price(Number(r.entry))}</td><td className="right num">{price(Number(r.exit))}</td>
                <td className="right num">{signedRupees(Number(r.gross))}</td><td className="right num">{rupees(Number(r.charges))}</td>
                <td className={`right num ${tone(Number(r.net))}`}>{signedRupees(Number(r.net))}</td><td className="small">{d.rules[r.rule] ?? r.rule}</td></tr>))}</tbody>
          </table></div></details>
      ) : <Empty>No closed intraday trades yet.</Empty>}
    </Panel>
  );
}

// ---------------------------------------------------------------- evidence
function Evidence() {
  const { data, error, reload } = useApi<EvidenceSet[]>("/api/intraday/evidence");
  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading height={100} />;
  const any = data.some((set) => set.variants.some((v) => v.passed));
  return (
    <Panel title="What the tests found" aside="Backtests on free 5-minute candles, with all charges and slippage included.">
      <div className={`notice ${any ? "up" : "warn"}`}>
        {any ? "At least one rule passed its test." : "No rule has passed its test yet."} The test was fixed before running: profit after charges in both halves of the period, profit factor 1.2 or better, and at least 40 trades.
        The period is only about {data[0]?.sessions ?? 59} trading days, so even a pass would need to be confirmed on new days. Treat everything on this page as an experiment.
      </div>
      {data.map((set) => (
        <div key={set.universe} className="table-wrap">
          <div className="small muted" style={{ margin: "6px 0" }}>{set.universe}: {set.from} to {set.to}, {set.sessions} sessions</div>
          <table>
            <thead><tr><th>Rule</th><th className="right">Trades</th><th className="right">Net</th><th className="right">Profit factor</th><th className="right">First / second half</th><th>Result</th></tr></thead>
            <tbody>{set.variants.map((v) => (
              <tr key={v.name}><td className="small">{v.name}</td><td className="right num">{v.trades}</td>
                <td className={`right num ${tone(v.net)}`}>{signedRupees(v.net)}</td><td className="right num">{v.profit_factor.toFixed(2)}</td>
                <td className="right num small">{signedRupees(v.first_half)} / {signedRupees(v.second_half)}</td>
                <td><Tag tone={v.passed ? "up" : "down"}>{v.passed ? "Pass" : "Not passed"}</Tag>{" "}
                  <span className="small muted">{v.why.join("; ")}</span></td></tr>))}</tbody>
          </table>
        </div>
      ))}
    </Panel>
  );
}

// ---------------------------------------------------------------- the page
export default function IntradayPage() {
  const guard = useApi<Guard>("/api/intraday/guard");
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  useEffect(() => { const timer = setInterval(guard.reload, 30000); return () => clearInterval(timer); }, [guard.reload]);

  const log = (c: IntradayCandidate) => {
    const sg = c.signal;
    setPrefill({ symbol: c.symbol, side: c.direction, qty: String(sg.qty ?? ""), entry: String(sg.entry ?? ""), stop: String(sg.stop ?? ""),
      target: String(sg.target ?? ""), rule: c.tier === "tested" ? "gap_go" : "gap_go_wide", key: Date.now() });
    document.getElementById("intraday-journal")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <>
      <h1>Intraday <Tag tone="warn">experimental</Tag></h1>
      <p className="small muted" style={{ marginTop: -8 }}>
        A separate lab from the swing model. It finds stocks to watch and works out the levels; you place the orders in Kite.
        No rule here has been proven (see "What the tests found" at the bottom).
      </p>
      <div className="stack">
        {guard.error ? <Problem error={guard.error} retry={guard.reload} /> : guard.data ? <DayGuard guard={guard.data} /> : <Loading height={90} />}
        {guard.data ? <ScanPanel guard={guard.data} onLog={log} /> : null}
        <ZerodhaSummary />
        <div id="intraday-journal"><Journal prefill={prefill} onChange={guard.reload} /></div>
        <Evidence />
      </div>
    </>
  );
}
