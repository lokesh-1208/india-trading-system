// Market: the model's market checks, world markets, institutional money, and the model's past.
import { Link } from "react-router-dom";
import { Market, useApi } from "../api";
import { useApp } from "../App";
import { Check, Loading, Panel, Problem, Tag } from "../components/ui";
import { LineChart } from "../components/PriceChart";
import { num, pct, share } from "../format";

function breadthNote(above20: number, above200: number) {
  const short = above20 >= 60 ? "Most stocks are rising in the short term" : above20 <= 40
    ? "Most stocks are falling in the short term" : "Stocks are split in the short term";
  const long = above200 >= 60 ? "and most are in long-term uptrends." : above200 <= 40
    ? "and most are below their long-term average." : "and about half are in long-term uptrends.";
  return `${short}, ${long} Broad rises (many stocks above their averages) are healthier than an index lifted by a few big names.`;
}

export default function MarketPage() {
  const { version, theme } = useApp();
  const { data, error, reload } = useApi<Market>("/api/market", version);
  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading count={3} height={160} />;
  const summary = data.history.summary;
  const passed = data.checks.filter((check) => check.passed).length;
  const known = data.checks.filter((check) => check.passed !== null).length;

  return (
    <>
      <section className="hero" aria-label="Market">
        <div className="panel plan">
          <span className="eyebrow">The model's market checks</span>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
            <h1>{passed} of {known} pass</h1>
            {known < data.checks.length ? <span className="muted">({data.checks.length - known} not known yet)</span> : null}
            <Tag tone={data.level === "strong" ? "up" : data.level === "caution" ? "warn" : "down"}>{data.level}</Tag>
          </div>
          <p className="muted">{data.note}</p>
        </div>
      </section>

      <div className="row">
        <div className="main-col">
          {data.breadth ? (
            <Panel title="Market breadth" aside="Nifty 500 stocks that trade enough, last 6 months">
              <div className="grid-tiles">
                <div className="tile"><span className="name">Above their 20-day average</span>
                  <span className="value num">{Math.round(data.breadth.above_20)}%</span>
                  <span className={`note ${data.breadth.above_20 >= data.breadth.above_20_week_ago ? "up" : "down"}`}>
                    {Math.round(data.breadth.above_20_week_ago)}% a week ago</span></div>
                <div className="tile"><span className="name">Above their 200-day average</span>
                  <span className="value num">{Math.round(data.breadth.above_200)}%</span>
                  <span className={`note ${data.breadth.above_200 >= data.breadth.above_200_week_ago ? "up" : "down"}`}>
                    {Math.round(data.breadth.above_200_week_ago)}% a week ago</span></div>
              </div>
              <LineChart theme={theme} unit="percent" height={220} label="Share of stocks above their averages, last 6 months" series={[
                { name: "Above 20-day", color: "--blue", points: data.breadth.series.map((point) => ({ time: point.time, value: point.above_20 })) },
                { name: "Above 200-day", color: "--warn", points: data.breadth.series.map((point) => ({ time: point.time, value: point.above_200 })) },
              ]} />
              <p className="small muted">{breadthNote(data.breadth.above_20, data.breadth.above_200)}</p>
            </Panel>
          ) : null}

          {data.sectors.length ? (
            <Panel title="Sector strength" aside="industries with 3 or more scored stocks, strongest month first">
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Industry</th><th className="right">Stocks</th><th className="right">1 month</th>
                    <th>Above 20-day average</th><th className="right">Model score</th></tr></thead>
                  <tbody>
                    {data.sectors.map((row) => (
                      <tr key={row.industry}>
                        <td>{row.industry}</td>
                        <td className="right num muted">{row.stocks}</td>
                        <td className={`right num ${row["month_%"] >= 0 ? "up" : "down"}`}>{pct(row["month_%"])}</td>
                        <td style={{ minWidth: 160 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div className="track" style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--track)" }}>
                              <div style={{ width: `${row["above_ema_%"]}%`, height: 8, borderRadius: 4,
                                background: row["above_ema_%"] >= 50 ? "var(--up)" : "var(--muted)" }} />
                            </div>
                            <span className="num small" style={{ width: 40, textAlign: "right" }}>{Math.round(row["above_ema_%"])}%</span>
                          </div>
                        </td>
                        <td className="right num">{Math.round(row.score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          ) : null}

          <Panel title="How the model did in the past" aside={`${summary.period_start} to ${summary.period_end}, after charges`}>
            <div className="grid-tiles">
              <div className="tile"><span className="name">Growth per year</span>
                <span className="value num">{share(summary.annual_growth_rate as number, 1, true)}</span>
                <span className="note">Nifty {share(summary.benchmark_annual_growth_rate as number, 1, true)}</span></div>
              <div className="tile"><span className="name">Worst fall</span>
                <span className="value num">{share(summary.max_drawdown as number)}</span>
                <span className="note">Nifty {share(summary.benchmark_max_drawdown as number)}</span></div>
              <div className="tile"><span className="name">Trades</span>
                <span className="value num">{summary.trades}</span>
                <span className="note">{share(summary.win_rate as number, 0)} made money</span></div>
              <div className="tile"><span className="name">Charges paid</span>
                <span className="value num">₹{num(summary.total_charges as number, 0)}</span>
                <span className="note">brokerage, taxes, fees</span></div>
            </div>
            <LineChart theme={theme} series={[
              { name: "Model", color: "--blue", points: data.history.equity.map((point) => ({ time: point.time, value: point.model })) },
              { name: "Nifty", color: "--muted", points: data.history.equity.map((point) => ({ time: point.time, value: point.nifty })) },
            ]} />
            <div className="table-wrap">
              <table>
                <thead><tr><th>Year</th><th className="right">Model</th><th className="right">Nifty</th></tr></thead>
                <tbody>
                  {data.history.by_year.map((row) => (
                    <tr key={row.year}><td>{row.year}</td>
                      <td className={`right num ${row.model >= 0 ? "up" : "down"}`}>{share(row.model, 1, true)}</td>
                      <td className="right num muted">{share(row.nifty, 1, true)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Same rules as the Today page. Under five years of history and most company data covers only
              the last few years, so this is not proof for real money.</p>
          </Panel>
        </div>
        <aside className="side-col">
          <Panel title="Market checks">
            <div className="checks">
              {data.checks.map((check) => <Check key={check.name} passed={check.passed}>{check.name}</Check>)}
            </div>
          </Panel>
          <Panel title="Avoid: weakest scores" aside="not to buy; leave if you hold one">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.avoid.map((item) => (
                <Link key={item.symbol} to={`/stocks/${item.symbol}`} className="pill"
                  style={{ background: "var(--down-bg)", color: "var(--text)" }}>
                  {item.symbol} <span className="muted small">score {Math.round(item.score)}</span>
                </Link>
              ))}
            </div>
          </Panel>
          <Panel title="Other markets" aside="last saved; Nifty, VIX, rupee and Brent are live at the top">
            {data.markets.map((market) => (
              <div key={market.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span className="muted">{market.name}</span>
                <span className="num">{num(market.value)} <span className={(market.name === "India VIX" ? -market.change : market.change) >= 0 ? "up" : "down"}>{pct(market.change, 2)}</span></span>
              </div>
            ))}
          </Panel>
          {data.fii_dii.length ? (
            <Panel title="Institutions' net buying" aside="₹ crore">
              <table>
                <thead><tr><th>Day</th><th className="right">Foreign</th><th className="right">Indian</th></tr></thead>
                <tbody>
                  {data.fii_dii.slice().reverse().slice(0, 8).map((row) => (
                    <tr key={row.date}><td className="small">{new Date(row.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</td>
                      <td className={`right num ${(row.FII ?? 0) >= 0 ? "up" : "down"}`}>{num(row.FII, 0)}</td>
                      <td className={`right num ${(row.DII ?? 0) >= 0 ? "up" : "down"}`}>{num(row.DII, 0)}</td></tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          ) : null}
        </aside>
      </div>
    </>
  );
}
