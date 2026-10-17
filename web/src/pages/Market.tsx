// Market: the model's market checks, world markets, institutional money, and the model's past.
import { Link } from "react-router-dom";
import { Market, useApi } from "../api";
import { useApp } from "../App";
import { Loading, Panel, Problem, Stat, Tag } from "../components/ui";
import { LineChart } from "../components/PriceChart";
import { day, num, pct, share } from "../format";

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

  const day0 = data.checks_day ? day(data.checks_day) : null;
  const flows = data.fii_dii.slice().reverse().slice(0, 10);
  const biggest = Math.max(1, ...flows.flatMap((row) => [Math.abs(row.FII ?? 0), Math.abs(row.DII ?? 0)]));
  const sameDay = (value?: string) => !value || !data.checks_day || value.slice(0, 10) === data.checks_day.slice(0, 10);

  return (
    <>
      <section className={`panel hero-plan level-${data.level === "strong" ? "strong" : data.level === "caution" ? "caution" : "weak"}`}
        aria-label="Market">
        <div className="hp-main">
          <span className="eyebrow">The model's market checks{day0 ? ` · at the ${day0} close` : ""}</span>
          <div className="hp-title">
            <h1>{passed} of {known} pass</h1>
            {known < data.checks.length ? <span className="muted">({data.checks.length - known} not known yet)</span> : null}
            <Tag tone={data.level === "strong" ? "up" : data.level === "caution" ? "warn" : "down"}>{data.level}</Tag>
          </div>
          <p className="muted small">{data.note}</p>
          <div className="check-grid" aria-label="Market checks">
            {data.checks.map((check) => (
              <div key={check.name} className={`check-card ${check.passed === null ? "unknown" : check.passed ? "pass" : "fail"}`}>
                <span className="mark" aria-hidden="true">{check.passed === null ? "–" : check.passed ? "✓" : "✕"}</span>
                <div>
                  <div className="name">{check.name}<span className="sr-only">: {check.passed === null ? "not known" : check.passed ? "passes" : "fails"}</span></div>
                  {check.detail ? <div className="small muted num">{check.detail}</div> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="tile-strip" aria-label="Other markets">
        {data.markets.map((market) => (
          <div key={market.name} className="mtile">
            <span className="name">{market.name}</span>
            <span className="value num">{num(market.value)}</span>
            <span className={`small num ${(market.name === "India VIX" ? -market.change : market.change) >= 0 ? "up" : "down"}`}>{pct(market.change, 2)}</span>
            {market.day ? <span className={`small ${sameDay(market.day) ? "muted" : "warn-text"}`}>{day(market.day)} close</span> : null}
          </div>
        ))}
      </div>

      <div className="grid-2">
        {data.breadth ? (
          <Panel title="Market breadth" aside={`at the ${day(data.breadth.day)} close`}>
            <div className="stat-row">
              <Stat name="Above their 20-day average" value={`${Math.round(data.breadth.above_20)}%`}
                note={`${Math.round(data.breadth.above_20_week_ago)}% a week ago`}
                tone={data.breadth.above_20 >= data.breadth.above_20_week_ago ? "up" : "down"} />
              <Stat name="Above their 200-day average" value={`${Math.round(data.breadth.above_200)}%`}
                note={`${Math.round(data.breadth.above_200_week_ago)}% a week ago`}
                tone={data.breadth.above_200 >= data.breadth.above_200_week_ago ? "up" : "down"} />
            </div>
            <LineChart theme={theme} unit="percent" height={200} label="Share of stocks above their averages, last 6 months" series={[
              { name: "Above 20-day", color: "--blue", points: data.breadth.series.map((point) => ({ time: point.time, value: point.above_20 })) },
              { name: "Above 200-day", color: "--warn", points: data.breadth.series.map((point) => ({ time: point.time, value: point.above_200 })) },
            ]} />
            <p className="small muted">{breadthNote(data.breadth.above_20, data.breadth.above_200)}</p>
          </Panel>
        ) : null}
        {flows.length ? (
          <Panel title="Institutions' net buying" aside={`₹ crore · latest ${day(flows[0].date)}`}>
            <div className="flow-bars">
              <span className="small muted">Day</span><span className="small muted">Foreign (FII)</span><span className="small muted">Indian (DII)</span>
              {flows.map((row) => (
                <div key={row.date} style={{ display: "contents" }}>
                  <span className="small">{new Date(row.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
                  {[row.FII, row.DII].map((value, index) => (
                    <div key={index} className="flow-cell">
                      <div className="flow-track">
                        <div className={`flow-fill ${(value ?? 0) >= 0 ? "pos" : "neg"}`}
                          style={{ width: `${(Math.abs(value ?? 0) / biggest) * 50}%` }} />
                      </div>
                      <span className={`num small ${(value ?? 0) >= 0 ? "up" : "down"}`}>{num(value, 0)}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </Panel>
        ) : null}
      </div>

      {data.sectors.length ? (
        <Panel title="Sector strength" aside="industries with 3+ scored stocks · colour is the 1-month move · bar is the share above the 20-day average">
          <div className="heat-grid">
            {data.sectors.map((row) => {
              const move = row["month_%"];
              const strength = Math.min(1, Math.abs(move) / 8);
              return (
                <div key={row.industry} className="heat" style={{
                  background: `color-mix(in srgb, var(${move >= 0 ? "--up" : "--down"}) ${Math.round(10 + strength * 35)}%, var(--panel))`,
                }}>
                  <span className="name">{row.industry}</span>
                  <span className="num strong">{pct(move)}</span>
                  <div className="heat-bar"><div style={{ width: `${row["above_ema_%"]}%` }} /></div>
                  <span className="small muted num">{Math.round(row["above_ema_%"])}% above · score {Math.round(row.score)} · {row.stocks} stocks</span>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}

      <Panel title="Avoid: weakest scores" aside="not to buy; leave if you hold one">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {data.avoid.map((item) => (
            <Link key={item.symbol} to={`/stocks/${item.symbol}`} className="pill avoid">
              {item.symbol} <span className="muted small">score {Math.round(item.score)}</span>
            </Link>
          ))}
        </div>
      </Panel>

      <Panel title="How the model did in the past" aside={`${summary.period_start} to ${summary.period_end}, after charges`}>
        <div className="stat-row">
          <Stat name="Growth per year" value={share(summary.annual_growth_rate as number, 1, true)}
            note={`Nifty ${share(summary.benchmark_annual_growth_rate as number, 1, true)}`} />
          <Stat name="Worst fall" value={share(summary.max_drawdown as number)}
            note={`Nifty ${share(summary.benchmark_max_drawdown as number)}`} />
          <Stat name="Trades" value={summary.trades} note={`${share(summary.win_rate as number, 0)} made money`} />
          <Stat name="Charges paid" value={`₹${num(summary.total_charges as number, 0)}`} note="brokerage, taxes, fees" />
        </div>
        <LineChart theme={theme} series={[
          { name: "Model", color: "--blue", points: data.history.equity.map((point) => ({ time: point.time, value: point.model })) },
          { name: "Nifty", color: "--muted", points: data.history.equity.map((point) => ({ time: point.time, value: point.nifty })) },
        ]} />
        <div className="year-row">
          {data.history.by_year.map((row) => (
            <div key={row.year} className="year">
              <span className="small muted">{row.year}</span>
              <span className={`num strong ${row.model >= 0 ? "up" : "down"}`}>{share(row.model, 1, true)}</span>
              <span className="small muted num">Nifty {share(row.nifty, 1, true)}</span>
            </div>
          ))}
        </div>
        <p className="small muted">Same rules as the Today page. Under five years of history and most company data covers only
          the last few years, so this is not proof for real money.</p>
      </Panel>
    </>
  );
}
