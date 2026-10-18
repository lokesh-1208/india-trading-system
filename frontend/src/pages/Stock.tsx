// One stock: price chart, where it stands for you, the model's view and the business numbers.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bars as BarsData, StockPage, useApi } from "../api";
import { useApp } from "../App";
import PriceChart from "../components/PriceChart";
import { Bars, Check, Empty, Loading, Panel, Problem, Tag } from "../components/ui";
import { crore, dateTime, day, num, pct, price, share } from "../format";

const PERIODS: [string, number | null][] = [["1M", 22], ["6M", 126], ["1Y", 252], ["3Y", 756], ["All", null]];

function Tile({ name, value, note, tone }: { name: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="tile">
      <span className="name">{name}</span>
      <span className="value num">{value}</span>
      {note ? <span className={`note ${tone ?? ""}`}>{note}</span> : null}
    </div>
  );
}

export default function StockPageView() {
  const { symbol = "RELIANCE" } = useParams();
  const { version, theme } = useApp();
  const [period, setPeriod] = useState("6M");
  const days = PERIODS.find(([label]) => label === period)?.[1];
  const page = useApi<StockPage>(`/api/stocks/${symbol}`, version);
  const bars = useApi<BarsData>(`/api/stocks/${symbol}/prices${days ? `?days=${days}` : ""}`, version);
  const reports = useApi<{ year: string; link: string; size: string }[]>(`/api/stocks/${symbol}/reports`);

  const levels = useMemo(() => {
    const found = page.data?.levels ?? {};
    const lines = [];
    if (found.limit) lines.push({ price: found.limit, title: "buy limit", color: "#4c8dff" });
    if (found.bought) lines.push({ price: found.bought, title: "bought", color: "#9ba3b1" });
    if (found.stop) lines.push({ price: found.stop, title: "stop-loss", color: "#f2655c" });
    return lines;
  }, [page.data]);

  if (page.error) return <Problem error={page.error} retry={page.reload} />;
  if (!page.data) return <Loading count={3} height={160} />;
  const data = page.data;
  const card = data.card as Record<string, number | null>;
  const fin = data.financial;
  const red = data.pledged_pct !== null && data.pledged_pct >= data.pledge_red_flag;

  return (
    <>
      <section aria-label={data.symbol} style={{ display: "flex", flexWrap: "wrap", gap: "12px 28px", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Link to="/" className="small">← Back to Today</Link>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 14px" }}>
            <h1>{data.symbol}</h1>
            <span className="muted">{data.industry || "Industry not known"}</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {data.stands.map((stand) => (
              <Tag key={stand.kind} tone={stand.kind === "weekly" ? "blue" : stand.kind === "held" ? "up" : stand.kind === "avoid" ? "down" : "plain"}>{stand.text}</Tag>
            ))}
            {data.model ? <Tag>Rank {data.model.rank} of {data.model.of} · score {Math.round(data.model.score)}</Tag> : <Tag>Not scored by the model</Tag>}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <span className="num" style={{ fontSize: 30, fontWeight: 600 }}>₹{price(data.price)}</span>
          <span className={`num ${data.change >= 0 ? "up" : "down"}`}>
            {data.change >= 0 ? "+" : "−"}{price(Math.abs(data.change))} ({pct(data.change_pct, 2)}) · {day(data.as_of)}
          </span>
        </div>
      </section>

      {red ? (
        <div className="notice warn" role="alert">
          <strong>Red flag:</strong> promoters have pledged {num(data.pledged_pct, 1)}% of their shares. If the price falls,
          lenders can sell them, pushing the price down further.
        </div>
      ) : null}

      <div className="row">
        <div className="main-col">
          <Panel>
            <div className="section-head">
              <div className="seg" role="group" aria-label="Period">
                {PERIODS.map(([label]) => (
                  <button key={label} aria-pressed={period === label} onClick={() => setPeriod(label)}>{label}</button>
                ))}
              </div>
              <div className="legend">
                <span><i style={{ background: "var(--warn)" }} />20-day average {price(data.trend_line)}</span>
                {data.levels.limit ? <span><i style={{ background: "#4c8dff" }} />buy limit</span> : null}
                {data.levels.stop ? <span><i style={{ background: "#f2655c" }} />stop-loss</span> : null}
              </div>
            </div>
            {bars.data ? <PriceChart data={bars.data} levels={levels} theme={theme} /> : <Loading height={400} />}
            <span className="small muted">Charts by TradingView lightweight-charts.</span>
          </Panel>

          <section className="section" aria-labelledby="business-title">
            <div className="section-head">
              <h2 id="business-title">The business</h2>
              <span className="small muted">
                {card.results_filed ? `${new Date(card.quarter as unknown as string).toLocaleDateString("en-IN", { month: "short", year: "numeric" })} quarter filed with NSE ${dateTime(card.results_filed as unknown as string)}` : ""}
                {data.next_results ? ` · next results ${day(data.next_results)}` : ""}
              </span>
            </div>
            <div className="grid-tiles">
              <Tile name="Market value" value={crore(card.market_cap_crore)} note={`${share(card.below_52w_high, 0)} from its 52-week high`} />
              <Tile name="PE" value={num(card.pe, 1)} note={card.industry_pe ? `industry ${num(card.industry_pe, 1)}` : undefined}
                tone={card.pe && card.industry_pe ? (card.pe <= card.industry_pe ? "up" : "down") : undefined} />
              <Tile name="Return on equity" value={share(card.return_on_equity)} note="last full year" />
              <Tile name="ROCE" value={fin ? "–" : share(card.roce)} note={fin ? "not used for finance companies" : "pass mark 15%"}
                tone={!fin && card.roce !== null ? (card.roce >= 0.15 ? "up" : "down") : undefined} />
              <Tile name="Cash / profit, 3 years" value={fin ? "–" : num(card.cash_conversion, 2)}
                note={fin ? "not used for finance companies" : "below 0.8: profit not turning into cash"}
                tone={!fin && card.cash_conversion !== null ? (card.cash_conversion >= 0.8 ? "up" : "down") : undefined} />
              <Tile name="Debt to equity" value={fin ? "–" : num(card.debt_to_equity, 2)} note={fin ? "not used for finance companies" : undefined} />
              <Tile name="Sales growth" value={share(card.sales_growth_1y, 1, true)} note={`3 years: ${share(card.sales_growth_3y, 1, true)} a year`} />
              <Tile name="Profit growth" value={share(card.profit_growth_1y, 1, true)} note={`latest quarter: ${share(card.quarter_profit_growth, 0, true)}`} />
              <Tile name="Profit margin" value={share(card.net_margin)} />
              <Tile name="Dividend yield" value={share(card.dividend_yield)} note="last 12 months" />
              <Tile name="Promoter pledge" value={data.pledged_pct === null ? "–" : `${num(data.pledged_pct, 1)}%`}
                note={data.pledged_pct === null ? "not published" : "of promoters' shares"} tone={red ? "down" : undefined} />
              <Tile name="52-week range" value={`${price(card.low_52w)} – ${price(card.high_52w)}`} />
            </div>
          </section>

          <Panel title="News and deals" aside="last 90 days">
            {data.news.length === 0 && data.deals.length === 0 ? <span className="small muted">Nothing important.</span> : null}
            {data.news.map((item) => (
              <div key={item.time + item.what} style={{ display: "flex", gap: 12, fontSize: 13, paddingTop: 8, borderTop: "1px solid var(--line)" }}>
                <span className="small muted" style={{ width: 110, flex: "none" }}>{dateTime(item.time)}</span>
                <span style={{ flex: 1 }}><strong>{item.type}</strong> · {item.what}{" "}
                  {item.link ? <a href={item.link} target="_blank" rel="noreferrer">filing</a> : null}</span>
              </div>
            ))}
            {data.deals.map((deal) => (
              <div key={deal.date + deal.client} className="small" style={{ paddingTop: 8, borderTop: "1px solid var(--line)" }}>
                {day(deal.date)} · {deal.kind} deal: {deal.client} {deal.side.toLowerCase()} {num(deal.quantity, 0)} at ₹{price(deal.price)}
              </div>
            ))}
          </Panel>
        </div>

        <aside className="side-col" aria-label="Model view">
          <Panel title="Model view" aside={data.model ? `${Math.round(data.model.score)} / 100` : undefined}>
            {data.model ? (
              <>
                <Bars items={data.model.groups} />
                <div className="checks" style={{ marginTop: 6 }}>
                  {data.model.checks.map((check) => <Check key={check.name} passed={check.passed}>{check.name}</Check>)}
                </div>
                <span className="small muted">The model buys only when all three are true and the market allows buying.</span>
              </>
            ) : <Empty>Not a current Nifty 500 member, or it trades too little.</Empty>}
          </Panel>

          <Panel title={`Scorecard · ${data.scorecard.passed} of ${data.scorecard.total}`}>
            <div className="checks">
              {data.scorecard.checks.map((check) => <Check key={check.name} passed={check.passed}>{check.name}</Check>)}
            </div>
          </Panel>

          {data.owners ? (
            <Panel title="Who owns it" aside={`quarter to ${day(data.owners.quarter)}`}>
              {data.owners.groups.filter((group) => group.value !== null).map((group) => (
                <div key={group.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span className="muted">{group.name}</span>
                  <span className="num">{num(group.value, 2)}%{" "}
                    <span className={(group.change ?? 0) >= 0 ? "up" : "down"}>{group.change === null ? "" : `(${pct(group.change, 2)})`}</span></span>
                </div>
              ))}
            </Panel>
          ) : null}

          <Panel title="Reports and calls">
            {reports.data?.map((report) => (
              <a key={report.link} href={report.link} target="_blank" rel="noreferrer">Annual report {report.year}</a>
            ))}
            {data.calls.map((call) => (
              <a key={call.link + call.time} href={call.link} target="_blank" rel="noreferrer" className="small">
                {day(call.time, true)}: {call.what}
              </a>
            ))}
            {!reports.data?.length && !data.calls.length ? <span className="small muted">Nothing found on NSE.</span> : null}
          </Panel>

          {data.peers.length > 1 ? (
            <Panel title="Peers" aside={data.industry}>
              {data.peers.map((peer) => (
                <Link key={peer.symbol} to={`/stocks/${peer.symbol}`}
                  style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: peer.symbol === data.symbol ? "var(--blue)" : "var(--text)" }}>
                  <span>{peer.symbol}</span><span className="num muted">rank {peer.rank} · {Math.round(peer.score)}</span>
                </Link>
              ))}
            </Panel>
          ) : null}
        </aside>
      </div>
    </>
  );
}
