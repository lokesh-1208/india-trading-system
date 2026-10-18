// Today: what to buy and what to hold or sell. The one page to act from.
// Context (before the open, news, movers, market health) lives on the Market page.
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BeforeOpen, Holding, LivePrice, MoneyPlan, Movers, Sector, SectorStock, Today, WeekRow, useApi } from "../api";
import { useApp } from "../App";
import { Drawer, Empty, Ladder, Loading, Panel, Problem, Stat, Tabs, Tag } from "../components/ui";
import { clock, LiveNote, useLive } from "../components/live";
import { day, dateTime, pct, price, rupees, signedRupees } from "../format";

function savedMoney() {
  try { return Number(localStorage.getItem("kasauti-money")) || 100000; } catch { return 100000; }
}

function savedTab() {
  try { return localStorage.getItem("kasauti-today-tab") || "buy"; } catch { return "buy"; }
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

// One holding on one line: where it is now, and how far it is from its exit.
function HoldRow({ row, quote }: { row: Holding; quote?: LivePrice }) {
  const now = quote?.price ?? row.last_price;
  const gainPct = quote ? (quote.price / row.buy_price - 1) * 100 : row["gain_%"];
  const gainRs = quote ? (quote.price - row.buy_price) * row.quantity : row.gain_rs;
  const tone = row.action === "SELL" ? "down" : row.action === "WAIT" ? "plain" : "up";
  const label = row.action === "SELL" ? "Sell" : row.action === "WAIT" ? "Bought today" : "Hold";
  const room = row.exit_line ? (now / row.exit_line - 1) * 100 : null;
  const belowLine = room !== null && room < 0;
  const roomTone = room === null ? "" : room < 0 ? "down" : room < 2 ? "warn" : "up";
  return (
    <Link to={`/stocks/${row.symbol}`} className={`hold-row ${row.action === "SELL" ? "is-sell" : ""}`}
      aria-label={`${row.symbol}: ${label}`}>
      <div className="h-who">
        <div className="line1">
          <span className="symbol">{row.symbol}</span><Tag tone={tone}>{label}</Tag>
          {row.warning ? <Tag tone="warn">1 close below the line</Tag> : null}
          {row.weakest ? <Tag tone="down">Weakest scores</Tag> : null}
        </div>
        <span className="small muted">{row.quantity} @ ₹{price(row.buy_price)} · day {holdingDay(row.bought)}
          {row.industry ? ` · ${row.industry}` : ""}</span>
      </div>
      <div className="h-now">
        <span className="num strong">{quote ? <span className="small muted live-word">live </span> : null}₹{price(now)}</span>
        {row.action === "WAIT" && !quote ? <span className="small muted">checked after the close</span> : (
          <span className={`num small ${(gainPct ?? 0) >= 0 ? "up" : "down"}`}>{pct(gainPct)} · {signedRupees(gainRs)}</span>
        )}
      </div>
      <div className="h-exit">
        <span className="small muted" title="Sell after two closes in a row below this line">Exit line</span>
        <span className="num">₹{price(row.exit_line)}
          {room !== null ? <span className={`gap-chip ${roomTone}`}>{room >= 0 ? `${room.toFixed(1)}% above` : `${Math.abs(room).toFixed(1)}% below`}</span> : null}
        </span>
      </div>
      <div className="h-stop">
        <span className="small muted">GTT stop</span>
        <span className="num">₹{price(row.gtt)}</span>
        <span className={`small num ${row.exit_pct > 0 ? "up" : "down"}`}>{row.exit_pct > 0 ? "locks " : "risk "}{pct(row.exit_pct)}</span>
      </div>
      {row.action === "SELL" || row.warning || (belowLine && row.action === "HOLD") || (row.size_vs_plan != null && row.size_vs_plan > 1.5) ? (
        <div className="h-note">
          {row.action === "SELL" ? <span className="small down">{row.reason}: sell at tomorrow's open.</span> : null}
          {row.warning ? <span className="small warn-text">{row.reason}. If the next close is below ₹{price(row.exit_line)} too, it is a sell.</span> : null}
          {belowLine && row.action === "HOLD" && quote ? <span className="small down">{row.warning
            ? `Live price is below the sell line again. If today's close is below ₹${price(row.exit_line)}, sell at tomorrow's open.`
            : `Live price is below the sell line. The rule decides at the close: it sells only after two closes in a row below ₹${price(row.exit_line)}.`}</span> : null}
          {row.size_vs_plan != null && row.size_vs_plan > 1.5 ? (
            <span className="small down strong" data-testid="oversized">{row.size_vs_plan.toFixed(1)}× today's place size: bigger than the plan</span>
          ) : null}
        </div>
      ) : null}
    </Link>
  );
}

// The orders to place, from the money you actually have (the backtest's own sizing rule).
function OrdersPanel({ plan, quote }: { plan: MoneyPlan; quote: (s: string) => LivePrice | undefined }) {
  const [copied, setCopied] = useState(false);
  const text = plan.buys.map((item) => `${item.symbol}  BUY  ${item.shares}  LIMIT ${item.limit.toFixed(2)}`).join("\n");
  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 2000); })
      .catch(() => setCopied(false));
  };
  return (
    <section className="panel orders" data-testid="money-plan" aria-label="Today's orders">
      <div className="section-head">
        <h2>{plan.buys.length ? <>Put in now: {rupees(plan.spend)}</> : "No orders today"}</h2>
        {plan.buys.length ? (
          <button type="button" className="small" onClick={copy}>{copied ? "Copied" : "Copy orders"}</button>
        ) : null}
      </div>
      {plan.buys.length ? (
        <div className="table-wrap">
          <table className="order-table">
            <thead><tr><th>Stock</th><th className="right">Shares</th><th className="right">AMO limit</th>
              <th className="right">Amount</th><th className="right">Now</th></tr></thead>
            <tbody>
              {plan.buys.map((item) => {
                const now = quote(item.symbol);
                const above = now !== undefined && now.price > item.limit;
                return (
                  <tr key={item.symbol} data-testid={`order-${item.symbol}`}>
                    <td><Link to={`/stocks/${item.symbol}`} className="strong-link">{item.symbol}</Link></td>
                    <td className="right num strong">{item.shares}</td>
                    <td className="right num">₹{price(item.limit)}</td>
                    <td className="right num">{rupees(item.amount)}</td>
                    <td className="right num">{now ? <><span className={above ? "warn-text" : "up"}>₹{price(now.price)}</span>
                      <div className="small muted">{above ? "above limit" : "in range"}</div></> : <span className="muted">–</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="small muted">{plan.note}</p>
      {plan.warning ? <p className="small down strong" data-testid="money-warning">{plan.warning}</p> : null}
    </section>
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
  "Results soon": "warn", "Too costly": "plain", "Market weak": "warn", "Monday only": "plain",
};

// One short reason per status, on one line (the full sentence is in the tooltip).
function shortWhy(row: WeekRow) {
  switch (row.status) {
    case "Missed": return `ran past ₹${price(row.limit)}`;
    case "Trend broke": return "below 20-day avg";
    case "Results soon": return "results within 5 days";
    case "Too costly": return "one share > amount";
    case "Monday only": return "bought only at Monday's open";
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

// The weekly list by sector: the top 10 plus the best of every other sector, so money can
// be spread across sectors. Buying a sector pick is your own choice: the backtest only
// tested buying from the top 10.
function SectorTable({ sectors, quote, stopPct, perSector, minScore, single = false }: {
  sectors: Sector[]; quote: (s: string) => LivePrice | undefined; stopPct: number;
  perSector: number; minScore: number; single?: boolean;
}) {
  const extra = sectors.reduce((count, sector) => count + sector.stocks.filter((s) => s.group === "sector").length, 0);
  return (
    <div className="table-wrap">
      {single ? (
        <p className="small muted" style={{ margin: "0 14px 10px" }}>
          {sectors[0].stocks.length} on this week's list{sectors[0].in_top ? `, ${sectors[0].in_top} of them in the top 10` : ""}.
          Same limit (+2% over the list close) and stop (−{Math.round(stopPct * 100)}%) as the top 10.
        </p>
      ) : <p className="small muted" style={{ margin: "0 14px 10px" }}>
        {sectors.length} sectors · the top 10 plus {extra} sector picks: the best {perSector} of each sector
        (score {minScore}+, above the 20-day average, no results due). Same limit (+2% over the list close)
        and stop (−{Math.round(stopPct * 100)}%) as the top 10. Sector picks were not part of the
        backtest, so how much goes into each is your call.
      </p>}
      <table className="week-table sector-table">
        <thead>
          <tr>
            <th>Stock</th>
            <th>Today</th>
            <th className="right">Stop</th>
            <th className="right">Limit</th>
            <th className="right">Live</th>
            <th className="right">Shares</th>
          </tr>
        </thead>
        {sectors.map((sector) => (
          <tbody key={sector.industry}>
            {single ? null : <tr className="sector-head">
              <td colSpan={6}>
                <strong>{sector.industry}</strong>{" "}
                <span className="small muted">· {sector.stocks.length} stock{sector.stocks.length !== 1 ? "s" : ""}
                  {sector.in_top ? ` · ${sector.in_top} in the top 10` : ""}</span>
              </td>
            </tr>}
            {sector.stocks.map((stock) => {
              const now = quote(stock.symbol);
              const buyable = stock.status === "Buy" || stock.status === "Monday only";
              const above = now !== undefined && now.price > stock.ladder.limit;
              const change = now?.["change_%"];
              return (
                <tr key={stock.symbol}>
                  <td>
                    <Link to={`/stocks/${stock.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{stock.symbol}</Link>
                    {" "}<Tag tone={stock.group === "top" ? "blue" : "plain"}>{stock.group === "top" ? "Top 10" : "Sector"}</Tag>
                    <div className="small muted">Rank {stock.rank} · score {Math.round(stock.score)}</div>
                  </td>
                  <td title={stock.why || undefined}>
                    {buyable && now ? <Tag tone={above ? "warn" : "up"}>{above ? "Above limit now" : "In range now"}</Tag>
                      : <Tag tone={STATUS_TONE[stock.status] ?? "plain"}>{stock.status === "Buy" ? "In range" : stock.status}</Tag>}
                    {!buyable && stock.why ? <div className="small muted">{stock.why}</div> : null}
                  </td>
                  <td className="right num down">₹{price(stock.ladder.stop)}</td>
                  <td className="right num">₹{price(stock.ladder.limit)}</td>
                  <td className="right num">
                    {now ? <>₹{price(now.price)}{" "}
                      {change != null ? <span className={change >= 0 ? "up" : "down"}>{pct(change, 1)}</span> : null}</>
                      : <>₹{price(stock.ladder.last)} <span className="small muted">close</span></>}
                  </td>
                  <td className="right num">
                    {stock.shares > 0 ? <>{stock.shares}<div className="small muted">about {rupees(stock.amount)}</div></>
                      : <span className="muted">–</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        ))}
      </table>
    </div>
  );
}

// How a stock on the sector list stands today, in two or three words.
function sectorState(stock: SectorStock, now?: LivePrice): [string, string] {
  const buyable = stock.status === "Buy" || stock.status === "Monday only";
  if (buyable && now) return now.price > stock.ladder.limit ? ["Above limit", "warn"] : ["In range", "up"];
  if (stock.status === "Buy") return ["In range", "up"];
  return [stock.status, STATUS_TONE[stock.status] ?? "plain"];
}

// Every sector on one screen: a small card each, the full list in a side panel on click.
function SectorGrid({ sectors, holds, quote, stopPct, perSector, minScore }: {
  sectors: Sector[]; holds: Holding[]; quote: (s: string) => LivePrice | undefined; stopPct: number;
  perSector: number; minScore: number;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const heldBy = new Map<string, string[]>();
  holds.forEach((row) => {
    const name = row.industry || "Other";
    heldBy.set(name, [...(heldBy.get(name) ?? []), row.symbol]);
  });
  const chosen = sectors.find((sector) => sector.industry === open);
  return (
    <>
      {heldBy.size ? (
        <div className="held-spread" data-testid="held-spread">
          <span className="small muted">Your money by sector:</span>
          {Array.from(heldBy.entries()).map(([name, symbols]) => (
            <span key={name} className="chip">{name} <strong>{symbols.length}</strong></span>
          ))}
        </div>
      ) : null}
      <div className="sector-grid">
        {sectors.map((sector) => {
          const held = heldBy.get(sector.industry) ?? [];
          const best = sector.stocks[0];
          return (
            <button key={sector.industry} type="button" className={`sector-card ${held.length ? "held" : ""}`}
              onClick={() => setOpen(sector.industry)} aria-label={`${sector.industry}: ${sector.stocks.length} stocks`}>
              <div className="sc-head">
                <span className="sc-name">{sector.industry}</span>
                <span className="sc-count num">{sector.stocks.length}</span>
              </div>
              <div className="sc-badges">
                {sector.in_top ? <Tag tone="blue">{sector.in_top} in top 10</Tag> : null}
                {held.length ? <Tag tone="up">You hold {held.length}</Tag> : null}
              </div>
              <ul className="sc-list">
                {sector.stocks.slice(0, 3).map((stock) => {
                  const [text, tone] = sectorState(stock, quote(stock.symbol));
                  return (
                    <li key={stock.symbol}>
                      <span className="sc-sym">{stock.symbol}</span>
                      <span className="num small muted">{Math.round(stock.score)}</span>
                      <span className={`dot-label ${tone}`}>{text}</span>
                    </li>
                  );
                })}
              </ul>
              <span className="sc-more small muted">
                {sector.stocks.length > 3 ? `+${sector.stocks.length - 3} more · ` : ""}best {best ? best.symbol : "–"} · open ›
              </span>
            </button>
          );
        })}
      </div>
      <p className="small muted">
        The best {perSector} of each sector (score {minScore}+, above the 20-day average, no results due), same +2% limit
        and −{Math.round(stopPct * 100)}% stop as the top 10. Sector picks were not part of the backtest, so buying them is your call.
      </p>
      {chosen ? (
        <Drawer title={chosen.industry} onClose={close}>
          <SectorTable sectors={[chosen]} quote={quote} stopPct={stopPct} perSector={perSector} minScore={minScore} single />
        </Drawer>
      ) : null}
    </>
  );
}

function countBy(rows: WeekRow[]) {
  const counts = new Map<string, number>();
  rows.forEach((row) => counts.set(row.status, (counts.get(row.status) ?? 0) + 1));
  return Array.from(counts.entries()).map(([status, count]) => `${count} ${status.toLowerCase()}`).join(" · ");
}

// The short reason behind a caution or weak market, without repeating the check count.
function marketReason(note: string, ok: boolean) {
  if (!ok) return "Too few checks pass: no new buys.";
  return /200-day/.test(note) && /below/.test(note) ? "Nifty is below its 200-day average: smaller amounts, or wait."
    : "Consider smaller amounts or waiting.";
}

export default function TodayPage() {
  const { version, status, startJob, job } = useApp();
  const [money, setMoney] = useState(savedMoney);
  const [tab, setTab] = useState(savedTab);
  const { data, error, reload } = useApi<Today>(`/api/today?money=${money}`, version);
  const symbols = useMemo(() => data
    ? Array.from(new Set([...data.holds.map((row) => row.symbol), ...data.week_list.map((row) => row.symbol),
      ...(data.sectors ?? []).flatMap((sector) => sector.stocks.map((stock) => stock.symbol))]))
    : [], [data]);
  const { live, failed: liveFailed } = useLive(symbols);
  const quote = (symbol: string) => live?.prices[symbol];

  const changeMoney = (value: number) => {
    setMoney(value);
    try { localStorage.setItem("kasauti-money", String(value)); } catch { /* private window */ }
  };
  const changeTab = (value: string) => {
    setTab(value);
    try { localStorage.setItem("kasauti-today-tab", value); } catch { /* private window */ }
  };

  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading count={4} height={110} />;
  const market = data.market;
  const caution = market.level !== "strong";
  const morning = beforeOpen();
  const plan = data.money_plan;
  const level = !market.ok ? "weak" : caution ? "caution" : "strong";
  const sectors = data.sectors ?? [];
  const tabs = [
    { id: "buy", label: "This week's buys", count: data.buys.length },
    ...(sectors.length ? [{ id: "sectors", label: "Best by sector", count: sectors.length }] : []),
    ...(data.week_list.length ? [{ id: "week", label: "Week tracker", count: data.week_list.length }] : []),
  ];
  const shown = tabs.some((item) => item.id === tab) ? tab : "buy";

  return (
    <>
      <section className={`panel hero-plan level-${level}`} aria-label="Today's plan">
        <div className="hp-main">
          <span className="eyebrow">For {day(data.list_day)} · from the {day(data.signal_day)} close</span>
          <div className="hp-title">
            <h1>{data.headline}</h1>
            {data.nothing_to_sell ? <span className="chip quiet">Nothing to sell</span> : null}
          </div>
          <div className="hp-market" title={market.note}>
            <Tag tone={!market.ok ? "down" : caution ? "warn" : "up"}>Market: {level}</Tag>
            <span className="small" data-testid="market-checks">
              {market.checks_pass} of {market.checks_total} market checks pass
              {market.checks_unknown.length ? ` (${market.checks_unknown.length} more not known yet)` : ""}
            </span>
            {caution ? <span className="small muted">· {marketReason(market.note, market.ok)}</span> : null}
          </div>
          <div className="stat-row">
            <Stat name="Trading money" value={rupees(plan.account)}
              note={plan.account !== plan.capital ? `${rupees(plan.capital)} set aside` : "set aside"} />
            <Stat name="In stocks" value={rupees(plan.holdings_value)} note={`cost ${rupees(plan.invested)}`} />
            <Stat name="Cash free" value={rupees(plan.cash)} note={`${plan.places} of ${market.positions} places free`} />
            <Stat name="Per stock now" value={rupees(plan.per_stock)}
              note={plan.share < 1 ? `${Math.round(plan.share * 100)}% of ${rupees(plan.per_stock / plan.share)}` : "a full place"}
              tone={plan.share < 1 ? "warn-text" : ""} />
            {plan.buys.length ? <Stat name="Stays as cash" value={rupees(plan.cash_after)}
              note={plan.open_places_after ? `${plan.open_places_after} place${plan.open_places_after > 1 ? "s" : ""} still free` : "all places full"} /> : null}
          </div>
          <p className="small muted" data-testid="next-list">
            This week's list was made from the {day(data.list_from)} close. Next list: {day(data.next_list)}, from the Friday close.
          </p>
        </div>
        <div className="hp-side">
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
          <div className="hp-buttons">
            <button className="primary" disabled={!!job?.running} onClick={() => startJob("daily")}>Update data</button>
            <button disabled={!!job?.running} onClick={() => startJob("premarket")}>Refresh before open</button>
          </div>
          {status?.updated ? <span className="small muted">Updated {dateTime(status.updated)} · daily 6:30 pm, before-open 9:10 am</span> : null}
        </div>
      </section>

      <div className="row">
        <div className="main-col">
          <div className="duo">
            {market.ok ? <OrdersPanel plan={plan} quote={quote} /> : (
              <section className="panel orders" aria-label="Today's orders">
                <h2>No orders today</h2>
                <p className="small muted">The market is weak, so the model buys nothing today.</p>
              </section>
            )}
            <section className="panel mine" id="mine" aria-labelledby="mine-title">
              <div className="section-head">
                <h2 id="mine-title">Your stocks</h2>
                {data.holds.length ? <span className="small muted">stop-loss {Math.round(market.stop_loss * 100)}% under your buy</span> : null}
              </div>
              {data.holds.length === 0 ? (
                <Empty>After you buy, record it under <Link to="/trades">Stocks &amp; trades</Link> and it shows here, marked Hold or Sell each day.</Empty>
              ) : data.holds.map((row) => <HoldRow key={row.symbol} row={row} quote={quote(row.symbol)} />)}
            </section>
          </div>

          <section className="panel list-panel" id="buy" aria-label="This week's list">
            <div className="list-head">
              <Tabs tabs={tabs} active={shown} onChange={changeTab} label="This week's list" />
              <span className="small muted">Limits from the {day(data.list_from)} close · place AMO limit orders</span>
            </div>
            {data.explain ? <p className="small muted" data-testid="list-explain">{data.explain}</p> : null}
            <p className="small muted live-line" data-testid="live-status">
              {liveFailed && !live ? "Live prices could not be fetched; showing the last close."
                : !live ? "Getting live prices…"
                  : live.market_open ? `Live prices, updated every minute (last at ${clock(live.time)}). The model still decides from the close.`
                    : "Market is closed: prices shown are the last traded ones."}
            </p>

            <div role="tabpanel" id={`panel-${shown}`} aria-labelledby={`tab-${shown}`}>
              {shown === "buy" ? (
                <div className="cards">
                  {!market.ok ? <Empty>The market is weak, so the model buys nothing today.</Empty>
                    : data.buys.length === 0 ? (data.buy_window && !data.buy_window.open
                      ? <Empty>No buys until {day(data.buy_window.next)}. The tested model buys only at the first open of the week; buying the week's picks on later days made results worse.</Empty>
                      : <Empty>Nothing on this week's list is buyable today.</Empty>)
                      : data.buys.map((item) => {
                        const now = quote(item.symbol);
                        const above = now !== undefined && now.price > item.ladder.limit;
                        return (
                          <Link key={item.symbol} to={`/stocks/${item.symbol}`} className={`card ${item.tag === "Buy" ? "is-pick" : ""}`}
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
                              <span className="num strong big">{item.shares} shares</span>
                              <span className="small muted">about {rupees(item.amount)}</span>
                              {item.size_share !== undefined && item.size_share < 0.99 ? (
                                <span className="small muted" title="Risk sizing: a jumpy stock gets a smaller amount, so a normal swing costs about 1% of your money">
                                  {Math.round(item.size_share * 100)}% of a full place (jumpy stock)</span>) : null}
                              <LiveNote quote={now} />
                            </div>
                          </Link>
                        );
                      })}
                  {data.results_due.length ? (
                    <p className="small muted">Left out because results are due within 5 days:{" "}
                      {data.results_due.map((item) => `${item.symbol} (${day(item.date)})`).join(", ")}.</p>
                  ) : null}
                </div>
              ) : null}

              {shown === "sectors" ? (
                <div id="sectors">
                  <SectorGrid sectors={sectors} holds={data.holds} quote={quote} stopPct={market.stop_loss}
                    perSector={data.sector_rules?.per_sector ?? 3} minScore={data.sector_rules?.min_score ?? 50} />
                </div>
              ) : null}

              {shown === "week" ? (
                <div id="week">
                  <p className="small muted">{data.week_list.length} stocks · {countBy(data.week_list)} · rank each day and move since picked</p>
                  <WeekTable rows={data.week_list} days={data.week_days} quote={quote} liveTime={live ? clock(live.time) : undefined} />
                  {data.watch.length ? (
                    <p className="small muted">
                      New on today's list, not this week's (watch only: buying new picks every day did worse in the tests):{" "}
                      {data.watch.map((item, index) => (
                        <span key={item.symbol}>{index ? ", " : ""}<Link to={`/stocks/${item.symbol}`}>{item.symbol}</Link></span>
                      ))}.
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>
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
