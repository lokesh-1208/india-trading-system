// Today: what to buy, what to hold or sell, and what to skip. The one page to act from.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BeforeOpen, getJson, Holding, Live, LivePrice, Movers, NewsIdeas, Today, useApi } from "../api";
import { useApp } from "../App";
import { Empty, Ladder, Loading, Panel, Problem, Section, Tag } from "../components/ui";
import { day, dateTime, pct, price, rupees, signedRupees } from "../format";

function savedMoney() {
  try { return Number(localStorage.getItem("kasauti-money")) || 100000; } catch { return 100000; }
}

const LIVE_EVERY_MS = 60_000;

// Live prices for the stocks on the page, asked again every minute while the page is open.
// They only show where a stock is now; the buy, hold and sell decisions come from the close.
function useLive(symbols: string[]) {
  const key = symbols.join(",");
  const [live, setLive] = useState<Live | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!key) return;
    let stopped = false;
    const ask = () => {
      if (document.visibilityState === "hidden") return;
      getJson<Live>(`/api/live?symbols=${encodeURIComponent(key)}`)
        .then((found) => { if (!stopped) { setLive(found); setFailed(false); } })
        .catch(() => { if (!stopped) setFailed(true); });
    };
    ask();
    const timer = window.setInterval(ask, LIVE_EVERY_MS);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [key]);
  return { live, failed };
}

function clock(value: string | null | undefined) {
  if (!value) return "";
  const time = value.slice(11, 16);
  return time ? time : "";
}

function LiveNote({ quote }: { quote?: LivePrice }) {
  if (!quote) return null;
  const change = quote["change_%"];
  return (
    <span className="small num" data-testid="live-price">
      <span className="muted">live</span> ₹{price(quote.price)}{" "}
      {change !== null ? <span className={change >= 0 ? "up" : "down"}>{pct(change, 1)}</span> : null}
      {quote.time ? <span className="muted"> · {clock(quote.time)}</span> : null}
    </span>
  );
}

// Trading days from the buy day to today, counting both (weekends skipped, holidays not known).
function holdingDay(bought: string, today = new Date()) {
  const day = new Date(`${bought.slice(0, 10)}T00:00:00`);
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  let count = 0;
  while (day <= end) {
    if (day.getDay() !== 0 && day.getDay() !== 6) count += 1;
    day.setDate(day.getDate() + 1);
  }
  return Math.max(count, 1);
}

function HoldCard({ row, quote }: { row: Holding; quote?: LivePrice }) {
  const now = quote?.price ?? row.last_price;
  const gainPct = quote ? (quote.price / row.buy_price - 1) * 100 : row["gain_%"];
  const gainRs = quote ? (quote.price - row.buy_price) * row.quantity : row.gain_rs;
  const tone = row.action === "SELL" ? "down" : row.action === "WAIT" ? "plain" : "up";
  const label = row.action === "SELL" ? "Sell" : row.action === "WAIT" ? "Bought today" : "Hold";
  return (
    <Link to={`/stocks/${row.symbol}`} className="card" aria-label={`${row.symbol}: ${label}`}>
      <div className="who">
        <div className="line1"><span className="symbol">{row.symbol}</span><Tag tone={tone}>{label}</Tag></div>
        <span className="small muted">{row.quantity} shares at ₹{price(row.buy_price)} · bought {day(row.bought)}</span>
        {row.action === "SELL" ? <span className="small down">{row.reason}: sell at tomorrow's open</span> : null}
      </div>
      <div className="mid facts">
        <span className="muted">Sell if it closes below</span><span className="num">₹{price(row.exit_line)}</span>
        <span className="muted">GTT stop-loss in Kite</span><span className="num">₹{price(row.gtt)}</span>
        <span className="muted">{row.exit_pct > 0 ? "Profit locked in" : "If it exits now"}</span>
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
      </div>
    </Link>
  );
}

function BeforeOpenCard({ version }: { version: number }) {
  const { data, error } = useApi<BeforeOpen>("/api/before-open", version);
  return (
    <Panel title="Before the open" aside={data ? `since ${dateTime(data.since)}` : undefined} id="before-open-card">
      {error ? <span className="small muted">{error}</span> : !data ? <Loading height={90} /> : (
        <>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{data.guess}</div>
          {data.moves.slice(0, 5).map((move) => (
            <div key={move.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="muted">{move.market}</span>
              <span className="num">{pct(move["change_%"], 2)}</span>
            </div>
          ))}
          {data.sectors.slice(0, 2).map((line) => <p key={line} className="small muted">{line}</p>)}
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

function NewsCard({ version }: { version: number }) {
  const { data, error } = useApi<NewsIdeas>("/api/news", version);
  const items = data ? [...data.exits.slice(0, 2), ...data.buys.slice(0, 2)] : [];
  return (
    <Panel title="News ideas" aside="for context">
      {error ? <span className="small muted">{error}</span> : !data ? <Loading height={90} /> : items.length === 0 ? (
        <span className="small muted">No news ideas in the last few days.</span>
      ) : (
        <>
          {items.map((idea) => (
            <div key={idea.symbol + idea.time} style={{ display: "flex", flexDirection: "column", gap: 2, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <Link to={`/stocks/${idea.symbol}`} style={{ fontWeight: 600, color: "var(--text)" }}>{idea.symbol}</Link>
                <span className={`small ${idea.lean > 0 ? "up" : "down"}`} style={{ fontWeight: 600 }}>
                  {idea.lean > 0 ? "Good news" : "Bad news"}
                </span>
              </div>
              <span style={{ fontSize: 13 }}>{idea.label}</span>
              <span className="small muted">{idea.history}</span>
            </div>
          ))}
          <Link to="/news" className="small">All news ideas</Link>
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
    <Panel title="Market mood" aside={day(data.day)}>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{mood.label}</div>
      <div className="meter" aria-hidden="true">
        <div style={{ width: `${(mood.rushing_in / total) * 100}%`, background: "var(--up)" }} />
        <div style={{ width: `${(mood.rushing_out / total) * 100}%`, background: "var(--down)" }} />
      </div>
      <div className="num small muted" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>{mood.rushing_in} heavy buying</span><span>{mood.rushing_out} heavy selling</span>
      </div>
      <p className="small muted">{mood.text} <Link to="/news">See the movers</Link></p>
    </Panel>
  );
}

export default function TodayPage() {
  const { version, status, startJob, job } = useApp();
  const [money, setMoney] = useState(savedMoney);
  const { data, error, reload } = useApi<Today>(`/api/today?money=${money}`, version);
  const symbols = useMemo(() => data
    ? [...data.buys, ...data.skips, ...data.holds].map((item) => item.symbol).sort() : [], [data]);
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

  return (
    <>
      <section className="hero" aria-label="Today's plan">
        <div className="panel plan">
          <span className="eyebrow">For {day(data.list_day)} · from the {day(data.signal_day)} close</span>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 20px" }}>
            <h1>{data.headline}</h1>
            {data.nothing_to_sell ? <span className="muted">Nothing to sell today</span> : null}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <Tag tone={!market.ok ? "down" : caution ? "warn" : "up"}>
              Market: {!market.ok ? "weak" : caution ? "caution" : "strong"}
            </Tag>
            <span className="small muted">
              {market.checks_pass} of {market.checks_total} market checks pass.{" "}
              {market.share < 1
                ? `Each buy uses ${Math.round(market.share * 100)}%: about ${rupees(market.per_stock)} instead of ${rupees(market.money / market.positions)}.`
                : `Each buy uses about ${rupees(market.per_stock)}.`}
            </span>
          </div>
          {caution ? <p className="small muted">{market.note}</p> : null}
        </div>
        <div className="panel data">
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="small muted">Data</span>
            <span>{status?.text ?? "…"}</span>
            {status?.updated ? <span className="small muted">Updated {dateTime(status.updated)} · daily update 6:30 pm, before-open 9:10 am</span> : null}
          </div>
          <label>Money for trading (₹)
            <input type="number" min={10000} step={5000} value={money}
              onChange={(event) => changeMoney(Number(event.target.value) || 100000)} />
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="primary" style={{ flex: "1 1 120px" }} disabled={!!job?.running}
              onClick={() => startJob("daily")}>Update data</button>
            <button style={{ flex: "1 1 120px" }} disabled={!!job?.running}
              onClick={() => startJob("premarket")}>Refresh before open</button>
          </div>
        </div>
      </section>

      <div className="row">
        <div className="main-col">
          <Section title="Buy from this week's list" id="buy"
            aside={`List made from the ${day(data.week_of)} close. Place an AMO limit order at the limit.`}>
            {data.explain ? <p className="small muted" data-testid="list-explain" style={{ marginTop: 0 }}>{data.explain}</p> : null}
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
              <Empty>After you buy, record it under <Link to="/trades">Trades</Link> and it shows here, marked Hold or Sell each day.</Empty>
            ) : data.holds.map((row) => <HoldCard key={row.symbol} row={row} quote={quote(row.symbol)} />)}
          </Section>

          {data.skips.length ? (
            <Section title={<>Not buyable now <span className="muted" style={{ fontWeight: 400 }}>· rest of this week's list</span></>} id="skip">
              <div className="panel tight table-wrap">
                <table>
                  <thead><tr><th>Stock</th><th>Status</th><th>Why</th><th className="right">Live</th></tr></thead>
                  <tbody>
                    {data.skips.map((item) => (
                      <tr key={item.symbol}>
                        <td><Link to={`/stocks/${item.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{item.symbol}</Link></td>
                        <td><span className={`small ${item.status === "Missed" ? "muted" : "down"}`} style={{ fontWeight: 600 }}>{item.status}</span></td>
                        <td className="small muted num">{item.why}</td>
                        <td className="right">
                          <LiveNote quote={quote(item.symbol)} />
                          {item.status === "Missed" && quote(item.symbol) && quote(item.symbol)!.price <= item.ladder.limit
                            ? <div className="small up" style={{ fontWeight: 600 }}>back in range</div> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          ) : null}

          {data.tracker.rows.length ? (
            <Section title="This week's tracker" id="tracker"
              aside="Rank on each day's list; change since first picked, against Nifty">
              <div className="panel tight table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Stock</th>
                      {data.tracker.days.map((list) => <th key={list} className="right">{day(list)}</th>)}
                      <th className="right">Since picked</th><th className="right">Nifty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tracker.rows.map((row) => (
                      <tr key={row.symbol}>
                        <td><Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link>
                          {row.last_week ? <span className="small muted"> · from last week</span> : null}</td>
                        {data.tracker.days.map((list) => {
                          const rank = Object.entries(row.ranks).find(([key]) => key.slice(0, 10) === list.slice(0, 10))?.[1];
                          return <td key={list} className="right num">{rank ?? <span className="muted">–</span>}</td>;
                        })}
                        <td className={`right num ${(row["since_first_%"] ?? 0) >= 0 ? "up" : "down"}`}>{pct(row["since_first_%"])}</td>
                        <td className="right num muted">{pct(row["nifty_%"])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          ) : null}

          {data.watch.length ? (
            <Section title="Watch: on today's list, not this week's" id="watch"
              aside="Buying new picks every day did worse in the tests than buying weekly">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {data.watch.map((item) => (
                  <Link key={item.symbol} to={`/stocks/${item.symbol}`} className="pill"
                    style={{ background: "var(--chip)", color: "var(--text)" }}>
                    {item.symbol} <span className="muted small">rank {item.rank}</span>
                  </Link>
                ))}
              </div>
            </Section>
          ) : null}

          <Section title="Avoid: weakest scores" id="avoid" aside="If you hold one, the model would rather you were out">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.avoid.map((item) => (
                <Link key={item.symbol} to={`/stocks/${item.symbol}`} className="pill"
                  style={{ background: "var(--down-bg)", color: "var(--text)" }}>
                  {item.symbol} <span className="muted small">score {Math.round(item.score)}</span>
                </Link>
              ))}
            </div>
          </Section>
        </div>

        <aside className="side-col" aria-label="Context">
          <BeforeOpenCard version={version} />
          <NewsCard version={version} />
          <MoodCard version={version} />
        </aside>
      </div>
      <p className="small muted">
        Buy, hold and sell follow the tested model. Before the open, news ideas and market mood are for context.
      </p>
    </>
  );
}
