// News ideas and market movers: what the news says, and where the crowd's money went.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Idea, Mover, Movers, NewsIdeas, useApi } from "../api";
import { useApp } from "../App";
import { Empty, Loading, Panel, Problem, Tag } from "../components/ui";
import { dateTime, day, pct } from "../format";

function IdeaTable({ rows }: { rows: Idea[] }) {
  if (rows.length === 0) return <Empty>None at the moment.</Empty>;
  return (
    <div className="panel tight table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th>News</th><th className="right">Since</th><th>Model</th><th>Idea</th><th>What usually happened</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol + row.time}>
              <td><Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link>
                <div className="small muted">{dateTime(row.time)}</div></td>
              <td style={{ maxWidth: 320 }}>
                <div className={row.lean > 0 ? "up" : "down"} style={{ fontWeight: 600 }}>{row.label}</div>
                <div className="small muted">{row.what}</div>
                {row.link ? <a className="small" href={row.link} target="_blank" rel="noreferrer">Open the filing</a> : null}
              </td>
              <td className={`right num ${(row["move_since_%"] ?? 0) >= 0 ? "up" : "down"}`}>{pct(row["move_since_%"])}</td>
              <td className="small">{row.view}{row.rank ? <span className="muted"> · rank {row.rank}</span> : null}</td>
              <td className="small" style={{ maxWidth: 260 }}>{row.idea}</td>
              <td className="small muted" style={{ maxWidth: 260 }}>{row.history}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MoverTable({ rows }: { rows: Mover[] }) {
  if (rows.length === 0) return <Empty>No stock moved this much on heavy volume.</Empty>;
  return (
    <div className="panel tight table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th className="right">Change</th><th className="right">Opened</th>
            <th className="right">Volume</th><th>Why (likely)</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol}>
              <td><Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link>
                <div className="small muted">{row.industry}</div></td>
              <td className={`right num ${row["change_%"] >= 0 ? "up" : "down"}`}>{pct(row["change_%"])}</td>
              <td className="right num muted">{pct(row["gap_%"])}</td>
              <td className="right num">{row.volume_x.toFixed(1)}×</td>
              <td className="small" style={{ maxWidth: 560 }}>{row.why}
                {row.link ? <> · <a href={row.link} target="_blank" rel="noreferrer">filing</a></> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function NewsPage() {
  const { version } = useApp();
  const ideas = useApi<NewsIdeas>("/api/news", version);
  const movers = useApi<Movers>("/api/movers", version);
  const [ideaSide, setIdeaSide] = useState<"buys" | "exits">("exits");
  const [moverSide, setMoverSide] = useState<"up" | "down">("up");

  return (
    <>
      <section className="section" aria-labelledby="ideas-title">
        <div className="section-head">
          <h1 id="ideas-title">News ideas <Tag tone="plain">for context</Tag></h1>
          {ideas.data ? (
            <div className="seg" role="group" aria-label="Which ideas">
              <button aria-pressed={ideaSide === "exits"} onClick={() => setIdeaSide("exits")}>Possible exits ({ideas.data.exits.length})</button>
              <button aria-pressed={ideaSide === "buys"} onClick={() => setIdeaSide("buys")}>Possible buys ({ideas.data.buys.length})</button>
            </div>
          ) : null}
        </div>
        {ideas.error ? <Problem error={ideas.error} retry={ideas.reload} /> : !ideas.data ? <Loading height={200} /> : (
          <>
            <p className="small muted">{ideas.data.note}</p>
            <IdeaTable rows={ideaSide === "buys" ? ideas.data.buys : ideas.data.exits} />
          </>
        )}
      </section>

      <section className="section" aria-labelledby="movers-title">
        <div className="section-head">
          <h2 id="movers-title">Market movers{movers.data?.day ? `, ${day(movers.data.day)}` : ""} <Tag tone="plain">for context</Tag></h2>
          {movers.data ? (
            <div className="seg" role="group" aria-label="Which side">
              <button aria-pressed={moverSide === "up"} onClick={() => setMoverSide("up")}>Heavy buying ({movers.data.up.length})</button>
              <button aria-pressed={moverSide === "down"} onClick={() => setMoverSide("down")}>Heavy selling ({movers.data.down.length})</button>
            </div>
          ) : null}
        </div>
        {movers.error ? <Problem error={movers.error} retry={movers.reload} /> : !movers.data ? <Loading height={200} /> : (
          <>
            {movers.data.mood ? (
              <p><strong>Mood: {movers.data.mood.label}.</strong> <span className="muted">{movers.data.mood.text}</span></p>
            ) : null}
            <p className="small muted">Nifty 500 stocks that moved at least {movers.data.rule.move}% on at least {movers.data.rule.volume}×
              their normal volume. Big moves often reverse in the following days.</p>
            <MoverTable rows={moverSide === "up" ? movers.data.up : movers.data.down} />
          </>
        )}
      </section>

      {ideas.data?.reactions.length ? (
        <Panel title="What usually happens after news" aside={`a year of NSE filings · ${ideas.data.days} trading days, against Nifty`}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Kind of news</th><th className="right">Past cases</th><th className="right">Average move</th><th className="right">Beat Nifty</th></tr></thead>
              <tbody>
                {ideas.data.reactions.map((row) => (
                  <tr key={row.group}>
                    <td>{row.group}</td>
                    <td className="right num">{row.cases}</td>
                    <td className={`right num ${row["average_%"] >= 0 ? "up" : "down"}`}>{pct(row["average_%"])}</td>
                    <td className="right num muted">{Math.round(row["beat_nifty_%"])}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}
    </>
  );
}
