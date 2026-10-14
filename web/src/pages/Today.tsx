// Today: what to buy and what to hold or sell. The one page to act from.
// Context (before the open, news, movers, market health) lives on the Market page.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BeforeOpen, Holding, LivePrice, MoneyPlan, Movers, Today, WeekRow, useApi } from "../api";
import { useApp } from "../App";
import { Empty, Ladder, Loading, Panel, Problem, Section, Tag } from "../components/ui";
import { clock, LiveNote, useLive } from "../components/live";
import { day, dateTime, pct, price, rupees, signedRupees } from "../format";

function savedMoney() {
  try { return Number(localStorage.getItem("kasauti-money")) || 100000; } catch { return 100000; }
}

// Before 9:15 am on a weekday (this computer's clock, India time).
function beforeOpen(now = new Date()) {
  const weekday = now.getDay() !== 0 && now.getDay() !== 6;
  return weekday && now.getHours() * 60 + now.getMinutes() < 9 * 60 + 15;
}

// Trading days from the buy day to today, counting both (weekends skipped, holidays not known).
function holdingDay(bought: string, today = new Date()) {
  const date = new Date(`${bought.slice(0, 10)}T00:00:00`);
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  let count = 0;
  while (date <= end) {
    if (date.getDay() !== 0 && date.getDay() !== 6) count += 1;
    date.setDate(date.getDate() + 1);
  }
  return Math.max(count, 1);
}

function HoldCard({ row, quote }: { row: Holding; quote?: LivePrice }) {
  const now = quote?.price ?? row.last_price;
  const gainPct = quote ? (quote.price / row.buy_price - 1) * 100 : row["gain_%"];
  const gainRs = quote ? (quote.price - row.buy_price) * row.quantity : row.gain_rs;
  const tone = row.action === "SELL" ? "down" : row.action === "WAIT" ? "plain" : "up";
  const label = row.action === "SELL" ? "Sell" : row.action === "WAIT" ? "Bought today" : "Hold";
  const nearLine = quote && row.action === "HOLD" && quote.price < row.exit_line;
  return (
    <Link to={`/stocks/${row.symbol}`} className="card" aria-label={`${row.symbol}: ${label}`}>
      <div className="who">
        <div className="line1">
          <span className="symbol">{row.symbol}</span><Tag tone={tone}>{label}</Tag>
          {row.weakest ? <Tag tone="down">Among the weakest scores</Tag> : null}
        </div>
        <span className="small muted">{row.quantity} shares at ₹{price(row.buy_price)} · bought {day(row.bought)}</span>
        {row.action === "SELL" ? <span className="small down">{row.reason}: sell at tomorrow's open</span> : null}
        {nearLine ? <span className="small down">Live price is below the sell line. The rule decides at the close: sell tomorrow only if it closes below ₹{price(row.exit_line)}.</span> : null}
      </div>
      <div className="mid facts">
        <span className="muted">Sell if it closes below</span><span className="num">₹{price(row.exit_line)}</span>
        <span className="muted">GTT stop-loss in Kite</span><span className="num">₹{price(row.gtt)}</span>
        {row.trail_from ? (
          <>
            <span className="muted">{row.trail_active ? "Profit trail on: high" : "Profit trail starts at"}</span>
            <span className={`num ${row.trail_active ? "up" : ""}`}>₹{price(row.trail_active ? row.peak : row.trail_from)}</span>
          </>
        ) : null}
        <span className="muted">{row.exit_pct > 0 ? "Profit locked in" : "If it exits there"}</span>
        <span className={`num ${row.exit_pct > 0 ? "up" : "down"}`}>{pct(row.exit_pct)} ({signedRupees(row.exit_rs)})</span>
      </div>
      <div className="end">
        <span className="num" style={{ fontSize: 16, fontWeight: 600 }}>
          {quote ? <span className="small muted" style={{ fontWeight: 400 }}>live </span> : null}₹{price(now)}
        </span>
        {row.action === "WAIT" && !quote ? <span className="small muted">checked after today's close</span> : (
          <span className={`num ${(gainPct ?? 0) >= 0 ? "up" : "down"}`} style={{ fontSize: 13 }}>
            {pct(gainPct)}  {signedRupees(gainRs)}
          </span>
        )}
        <span className="small muted">day {holdingDay(row.bought)} of holding</span>
        {row.size_vs_plan != null && row.size_vs_plan < 0.8 ? (
          <span className="small muted" title="The model never adds to a holding; this is for information.">
            {Math.round(row.size_vs_plan * 100)}% of today's place size
          </span>
        ) : null}
      </div>
    </Link>
  );
}

// How much to put in now, from the money you actually have (the backtest's own sizing rule).
function MoneyPlanPanel({ plan }: { plan: MoneyPlan }) {
  return (
    <div className="panel money" data-testid="money-plan">
      <div className="grid-tiles">
        <div className="tile"><span className="name">Your trading money</span>
          <span className="value num">{rupees(plan.account)}</span>
          <span className="note">{rupees(plan.capital)} set aside{plan.account !== plan.capital ? ", with gains and losses" : ""}</span></div>
        <div className="tile"><span className="name">In stocks</span>
          <span className="value num">{rupees(plan.holdings_value)}</span>
          <span className="note">cost {rupees(plan.invested)}</span></div>
        <div className="tile"><span className="name">Cash free</span>
          <span className="value num">{rupees(plan.cash)}</span>
          <span className="note">{plan.places} of 5 places free</span></div>
        <div className="tile"><span className="name">Per stock now</span>
          <span className="value num">{rupees(plan.per_stock)}</span>
          <span className="note">{plan.share < 1 ? `${Math.round(plan.share * 100)}% of a full place (caution)` : "a full place"}</span></div>
      </div>
      {plan.buys.length ? (
        <p style={{ margin: 0 }}>
          <strong>Put in now: {rupees(plan.spend)}</strong>{" "}
          <span className="muted">({plan.buys.map((item) => `${item.symbol} ${item.shares} shares at up to ₹${price(item.limit)}`).join(" · ")})</span>
        </p>
      ) : null}
      <p className="small muted" style={{ margin: 0 }}>{plan.note}</p>
    </div>
  );
}

function BeforeOpenCard({ version }: { version: number }) {
  const { data, error } = useApi<BeforeOpen>("/api/before-open", version);
  return (
    <Panel title="Before the open" aside={data ? `since ${dateTime(data.since)}` : undefined} id="before-open-card">
      {error ? <span className="small muted">{error}</span> : !data ? <Loading height={90} /> : (
        <>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{data.guess}</div>
          {data.moves.slice(0, 4).map((move) => (
            <div key={move.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="muted">{move.market}</span>
              <span className="num">{pct(move["change_%"], 2)}</span>
            </div>
          ))}
          <p className="small muted">
            {data.preopen_ready ? `${data.up.length} likely up, ${data.down.length} likely down at the open.`
              : "Pre-open prices appear after 9:08 am."}{" "}
            <Link to="/before-open">See all</Link>
          </p>
        </>
      )}
    </Panel>
  );
}

function MoodCard({ version }: { version: number }) {
  const { data } = useApi<Movers>("/api/movers", version);
  if (!data?.mood) return <Panel title="Market mood"><Loading height={70} /></Panel>;
  const mood = data.mood;
  const total = mood.rushing_in + mood.rushing_out || 1;
  return (
    <Panel title="Market mood" aside={`at the ${day(data.day)} close`}>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{mood.label}</div>
      <div className="meter" aria-hidden="true">
        <div style={{ width: `${(mood.rushing_in / total) * 100}%`, background: "var(--up)" }} />
        <div style={{ width: `${(mood.rushing_out / total) * 100}%`, background: "var(--down)" }} />
      </div>
      <div className="num small muted" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>{mood.rushing_in} heavy buying</span><span>{mood.rushing_out} heavy selling</span>
      </div>
      <p className="small muted">{mood.text} <Link to="/movers">See the movers</Link></p>
    </Panel>
  );
}

const STATUS_TONE: Record<string, string> = {
  Buy: "blue", Backup: "plain", "You hold": "up", Missed: "plain", "Trend broke": "down",
  "Results soon": "warn", "Too costly": "plain", "Market weak": "warn",
};

// One short reason per status, on one line (the full sentence is in the tooltip).
function shortWhy(row: WeekRow) {
  switch (row.status) {
    case "Missed": return `ran past ₹${price(row.limit)}`;
    case "Trend broke": return "below 20-day avg";
    case "Results soon": return "results within 5 days";
    case "Too costly": return "one share > amount";
    default: return "";
  }
}

function WeekTable({ rows, days, quote, liveTime }: {
  rows: WeekRow[]; days: string[]; quote: (s: string) => LivePrice | undefined; liveTime?: string;
}) {
  const dayNames = days.map((list) => new Date(list).toLocaleDateString("en-IN", { weekday: "short" }));
  return (
    <div className="table-wrap">
      <table className="week-table">
        <thead>
          <tr>
            <th>Stock</th>
            <th>Today</th>
            <th className="right">Live{liveTime ? ` · ${liveTime}` : ""}</th>
            <th className="right" title="Rank on each day's list this week">Rank {dayNames.join(" · ")}</th>
            <th className="right">Since picked</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const now = quote(row.symbol);
            const backInRange = row.status === "Missed" && now && now.price <= row.limit;
            const aboveNow = (row.status === "Buy" || row.status === "Backup") && now && now.price > row.limit;
            const change = now?.["change_%"];
            return (
              <tr key={row.symbol}>
                <td><Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link></td>
                <td title={row.why || undefined}>
                  <Tag tone={STATUS_TONE[row.status] ?? "plain"}>{row.status}</Tag>
                  {shortWhy(row) ? <span className="small muted"> {shortWhy(row)}</span> : null}
                </td>
                <td className="right num">
                  {now ? <>₹{price(now.price)}{" "}
                    {change != null ? <span className={change >= 0 ? "up" : "down"}>{pct(change, 1)}</span> : null}</>
                    : <span className="muted">–</span>}
                  {backInRange ? <div className="small up" style={{ fontWeight: 600 }}>back in range</div> : null}
                  {aboveNow ? <div className="small warn-text" style={{ fontWeight: 600 }}>above limit now</div> : null}
                </td>
                <td className="right num">
                  {days.map((list, index) => (
                    <span key={list}>{index ? <span className="muted"> · </span> : null}
                      {row.ranks[list] ?? <span className="muted">–</span>}</span>
                  ))}
                </td>
                <td className="right num">
                  <span className={(row["since_first_%"] ?? 0) >= 0 ? "up" : "down"}>{pct(row["since_first_%"])}</span>
                  <div className="small muted">Nifty {pct(row["nifty_%"])}</div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function countBy(rows: WeekRow[]) {
  const counts = new Map<string, number>();
  rows.forEach((row) => counts.set(row.status, (counts.get(row.status) ?? 0) + 1));
  return Array.from(counts.entries()).map(([status, count]) => `${count} ${status.toLowerCase()}`).join(" · ");
}

export default function TodayPage() {
  const { version, status, startJob, job } = useApp();
  const [money, setMoney] = useState(savedMoney);
  const { data, error, reload } = useApi<Today>(`/api/today?money=${money}`, version);
  const symbols = useMemo(() => data
    ? Array.from(new Set([...data.week_list.map((row) => row.symbol), ...data.holds.map((row) => row.symbol)])).sort()
    : [], [data]);
  const { live, failed: liveFailed } = useLive(symbols);
  const quote = (symbol: string) => live?.prices[symbol];

  const changeMoney = (value: number) => {
    setMoney(value);
    try { localStorage.setItem("kasauti-money", String(value)); } catch { /* private window */ }
  };

  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading count={4} height={110} />;
  const market = data.market;
  const caution = market.level !== "strong";
  const morning = beforeOpen();

  return (
    <>
      <section className="panel hero-one" aria-label="Today's plan">
        <div className="left">
          <span className="eyebrow">For {day(data.list_day)} · from the {day(data.signal_day)} close</span>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 20px" }}>
            <h1>{data.headline}</h1>
            {data.nothing_to_sell ? <span className="muted">Nothing to sell today</span> : null}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <Tag tone={!market.ok ? "down" : caution ? "warn" : "up"}>
              Market: {!market.ok ? "weak" : caution ? "caution" : "strong"}
            </Tag>
            <span className="small muted" data-testid="market-checks">
              {market.checks_pass} of {market.checks_total} market checks pass
              {market.checks_unknown.length ? ` (${market.checks_unknown.length} more not known yet)` : ""}.{" "}
              {market.share < 1
                ? `Each buy uses ${Math.round(market.share * 100)}%: about ${rupees(market.per_stock)} instead of ${rupees(market.per_stock / market.share)}.`
                : `Each buy uses about ${rupees(market.per_stock)}.`}
            </span>
          </div>
          {caution ? <p className="small muted">{market.note}</p> : null}
          <p className="small muted" data-testid="next-list">
            This week's list was made from the {day(data.list_from)} close. Next list: {day(data.next_list)}, from the Friday close.
          </p>
        </div>
        <div className="right">
          <span className="small">{status?.text ?? "…"}</span>
          {status?.missed_flow_days?.length ? (
            <span className="small warn-text" data-testid="missed-days">
              Daily update missed on {status.missed_flow_days.map((missed) => day(missed)).join(", ")}: that day's
              foreign/Indian institution figures are lost (NSE keeps only the latest day).
            </span>
          ) : null}
          <label className="small">Your total trading money (₹)
            <input type="number" min={10000} step={5000} value={money}
              onChange={(event) => changeMoney(Number(event.target.value) || 100000)} />
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="primary" style={{ flex: "1 1 120px" }} disabled={!!job?.running}
              onClick={() => startJob("daily")}>Update data</button>
            <button style={{ flex: "1 1 120px" }} disabled={!!job?.running}
              onClick={() => startJob("premarket")}>Refresh before open</button>
          </div>
          {status?.updated ? <span className="small muted">Updated {dateTime(status.updated)} · daily 6:30 pm, before-open 9:10 am</span> : null}
        </div>
      </section>

      <div className="row">
        <div className="main-col">
          <Section title="Buy from this week's list" id="buy"
            aside={`Limits from the ${day(data.list_from)} close. Place an AMO limit order at the limit.`}>
            {data.explain ? <p className="small muted" data-testid="list-explain" style={{ marginTop: 0 }}>{data.explain}</p> : null}
            {market.ok ? <MoneyPlanPanel plan={data.money_plan} /> : null}
            <p className="small muted" data-testid="live-status" style={{ marginTop: 0 }}>
              {liveFailed && !live ? "Live prices could not be fetched; showing the last close."
                : !live ? "Getting live prices…"
                  : live.market_open ? `Live prices, updated every minute (last at ${clock(live.time)}). The model still decides from the close.`
                    : "Market is closed: prices shown are the last traded ones."}
            </p>
            {!market.ok ? <Empty>The market is weak, so the model buys nothing today.</Empty>
              : data.buys.length === 0 ? <Empty>Nothing on this week's list is buyable today.</Empty>
                : data.buys.map((item) => {
                  const now = quote(item.symbol);
                  const above = now !== undefined && now.price > item.ladder.limit;
                  return (
                    <Link key={item.symbol} to={`/stocks/${item.symbol}`} className="card"
                      aria-label={`${item.symbol}: ${item.tag}`}>
                      <div className="who">
                        <div className="line1">
                          <span className="symbol">{item.symbol}</span>
                          <Tag tone={item.tag === "Buy" ? "blue" : "plain"}>{item.tag}</Tag>
                          {now ? <Tag tone={above ? "warn" : "up"}>{above ? "Above limit now" : "In range now"}</Tag> : null}
                        </div>
                        <span className="small muted">{item.about}</span>
                        {above ? <span className="small down">Live price is above the limit ₹{price(item.ladder.limit)}: do not chase. A limit order fills only if it comes back.</span> : null}
                      </div>
                      <div className="mid">
                        <Ladder ladder={now ? { ...item.ladder, last: now.price } : item.ladder} lastLabel={now ? "live" : "last"} />
                      </div>
                      <div className="end">
                        <span className="num" style={{ fontSize: 16, fontWeight: 600 }}>{item.shares} shares</span>
                        <span className="small muted">about {rupees(item.amount)}</span>
                        <LiveNote quote={now} />
                      </div>
                    </Link>
                  );
                })}
            {data.results_due.length ? (
              <p className="small muted">Left out because results are due within 5 days:{" "}
                {data.results_due.map((item) => `${item.symbol} (${day(item.date)})`).join(", ")}.</p>
            ) : null}
          </Section>

          <Section title="Your stocks" id="mine"
            aside={data.holds.length ? `Stop-loss ${Math.round(market.stop_loss * 100)}% under your buy price` : undefined}>
            {data.holds.length === 0 ? (
              <Empty>After you buy, record it under <Link to="/trades">Stocks &amp; trades</Link> and it shows here, marked Hold or Sell each day.</Empty>
            ) : data.holds.map((row) => <HoldCard key={row.symbol} row={row} quote={quote(row.symbol)} />)}
          </Section>

          {data.week_list.length ? (
            <details className="panel tight week" id="week">
              <summary>
                <strong>This week's list</strong>{" "}
                <span className="small muted">· {data.week_list.length} stocks · {countBy(data.week_list)} · ranks each day and move since picked</span>
              </summary>
              <WeekTable rows={data.week_list} days={data.week_days} quote={quote} liveTime={live ? clock(live.time) : undefined} />
              {data.watch.length ? (
                <p className="small muted" style={{ padding: "0 14px 12px" }}>
                  New on today's list, not this week's (watch only: buying new picks every day did worse in the tests):{" "}
                  {data.watch.map((item, index) => (
                    <span key={item.symbol}>{index ? ", " : ""}<Link to={`/stocks/${item.symbol}`}>{item.symbol}</Link></span>
                  ))}.
                </p>
              ) : null}
            </details>
          ) : null}
        </div>

        <aside className="side-col" aria-label="Context">
          {morning ? <BeforeOpenCard version={version} /> : null}
          <MoodCard version={version} />
          <Panel title="More context">
            <p className="small muted" style={{ margin: 0 }}>
              Before the open, news ideas, movers, market health and the weakest scores are on the{" "}
              <Link to="/market">Market</Link> page.
            </p>
          </Panel>
        </aside>
      </div>
      <p className="small muted">
        Buy, hold and sell follow the tested model. Market mood and everything on the Market page are for context.
      </p>
    </>
  );
}
