// Before the open: global markets since our close, overnight filings, and NSE's pre-open prices.
import { useState } from "react";
import { Link } from "react-router-dom";
import { BeforeOpen, Likely, useApi } from "../api";
import { useApp } from "../App";
import { Empty, Loading, Panel, Problem, Tag } from "../components/ui";
import { dateTime, day, pct } from "../format";

function LikelyTable({ rows }: { rows: Likely[] }) {
  if (rows.length === 0) return <Empty>Nothing found for this side.</Empty>;
  return (
    <div className="panel tight table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th className="right">Pre-open</th><th>Why</th><th>Model</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol}>
              <td>
                <Link to={`/stocks/${row.symbol}`} style={{ color: "var(--text)", fontWeight: 600 }}>{row.symbol}</Link>
                <div className="small muted">{row.industry}</div>
                {row.yours ? <Tag tone="warn">{row.yours === "held" ? "You hold it" : "This week's list"}</Tag> : null}
              </td>
              <td className={`right num ${(row.open_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(row.open_pct)}</td>
              <td style={{ maxWidth: 560 }}>
                {row.reasons.map((reason) => <div key={reason} className="small">{reason}</div>)}
                {row.link ? <a href={row.link} target="_blank" rel="noreferrer" className="small">Open the filing</a> : null}
              </td>
              <td className="small muted">{row.view}{row.rank ? ` (rank ${row.rank})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BeforeOpenPage() {
  const { version, startJob, job } = useApp();
  const { data, error, reload } = useApi<BeforeOpen>("/api/before-open", version);
  const [side, setSide] = useState<"up" | "down">("up");
  if (error) return <Problem error={error} retry={reload} />;
  if (!data) return <Loading count={3} height={140} />;
  const yours = [...data.up, ...data.down].filter((row) => row.yours);

  return (
    <>
      {data.stage === "open" || data.stage === "after" ? (
        <div className="notice warn" role="note" data-testid="stage-note">
          The market {data.stage === "open" ? "is open" : "has closed"}: these were this morning's guesses. For prices now,
          see the live prices on the Today page.
        </div>
      ) : null}
      <section className="hero" aria-label="Before the open">
        <div className="panel plan">
          <span className="eyebrow">Since the close on {dateTime(data.since)}</span>
          <h1>{data.guess}</h1>
          <p className="muted">{data.reasons.length ? data.reasons.join("; ") + "." : "No big global moves since the close."}</p>
          {data.sectors.map((line) => <p key={line} className="small">{line}</p>)}
          <p className="small muted">{data.note}</p>
        </div>
        <div className="panel data">
          <span className="small muted">{data.preopen_ready ? "NSE pre-open prices are in." : "NSE pre-open prices appear after 9:08 am."}</span>
          <button className="primary" disabled={!!job?.running} onClick={() => startJob("premarket")}>Refresh before open</button>
          <span className="small muted">Runs by itself at 9:10 am on weekdays.</span>
        </div>
      </section>

      {yours.map((row) => (
        <div key={row.symbol} className={`notice ${row.direction > 0 ? "up" : "down"}`}>
          <strong>{row.symbol}</strong> ({row.yours === "held" ? "you hold it" : "on this week's list"}):
          likely to open {row.direction > 0 ? "up" : "down"}. {row.reasons[0]}
        </div>
      ))}

      <div className="row">
        <div className="main-col">
          <div className="section-head">
            <h2>Stocks likely to move at the open</h2>
            <div className="seg" role="group" aria-label="Side">
              <button aria-pressed={side === "up"} onClick={() => setSide("up")}>Likely up ({data.up.length})</button>
              <button aria-pressed={side === "down"} onClick={() => setSide("down")}>Likely down ({data.down.length})</button>
            </div>
          </div>
          <LikelyTable rows={side === "up" ? data.up : data.down} />
          <p className="small muted">Order: the pre-open price counts most, then clearly good or bad news, then
            industries that usually follow a global move (rules of thumb). Whether a kind of news counts as good or bad
            is decided by what happened after it in the past year where there are enough cases.</p>
        </div>
        <aside className="side-col">
          <Panel title="Global markets since our close">
            {data.moves.length === 0 ? <span className="small muted">No market has traded since the close yet.</span> :
              data.moves.map((move) => (
                <div key={move.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span className="muted">{move.market} <span className="small">({day(move.day)})</span></span>
                  <span className="num">{pct(move["change_%"], 2)}</span>
                </div>
              ))}
          </Panel>
        </aside>
      </div>
    </>
  );
}
