// Small building blocks shared by the pages.
import { ReactNode, useEffect } from "react";
import { Ladder as LadderShape } from "../api";
import { price } from "../format";

export function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="24" height="24" rx="6" fill="none" stroke="#4c8dff" strokeWidth="2" />
      <path d="M7 17 L11 11 L15 14 L19 8" fill="none" stroke="#4c8dff" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Tag({ tone = "plain", children }: { tone?: string; children: ReactNode }) {
  return <span className={`tag ${tone}`}>{children}</span>;
}

export function Panel({ title, aside, children, id }: {
  title?: ReactNode; aside?: ReactNode; children: ReactNode; id?: string;
}) {
  return (
    <section className="panel" id={id} aria-label={typeof title === "string" ? title : undefined}
      style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {title ? (
        <div className="section-head">
          <h3>{title}</h3>
          {aside ? <span className="small muted">{aside}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** The price bar on a buy card: stop-loss, the buy zone up to the limit, and the last close. */
export function Ladder({ ladder, lastLabel = "last" }: { ladder: LadderShape; lastLabel?: string }) {
  const span = ladder.high - ladder.low || 1;
  const at = (value: number) => `${Math.max(0, Math.min(100, ((value - ladder.low) / span) * 100)).toFixed(1)}%`;
  const zoneLeft = at(ladder.stop);
  const zoneWidth = `${(((ladder.limit - ladder.stop) / span) * 100).toFixed(1)}%`;
  return (
    <div className="ladder">
      <div className="bar" role="img"
        aria-label={`Stop-loss ${price(ladder.stop)}, ${lastLabel} ${price(ladder.last)}, buy limit ${price(ladder.limit)}`}>
        <div className="zone" style={{ left: zoneLeft, width: zoneWidth }} />
        <div className="stop" style={{ left: at(ladder.stop) }} />
        <div className="dot" style={{ left: at(ladder.last) }} />
      </div>
      <div className="labels num">
        <span>stop {price(ladder.stop)}</span>
        <span>{lastLabel} {price(ladder.last)}</span>
        <span>limit {price(ladder.limit)}</span>
      </div>
    </div>
  );
}

export function Loading({ height = 120, count = 1 }: { height?: number; count?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}

export function Problem({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="notice down" role="alert">
      <strong>Could not load this.</strong> {error}{" "}
      {retry ? <button className="small" onClick={retry}>Try again</button> : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Check({ passed, children }: { passed: boolean | null; children: ReactNode }) {
  const mark = passed === null ? ["–", "muted"] : passed ? ["Yes", "up"] : ["No", "down"];
  return (
    <div className="check">
      <span className={`mark ${mark[1]}`}>{mark[0]}</span>
      <span>{children}</span>
    </div>
  );
}

export function Bars({ items }: { items: { name: string; value: number }[] }) {
  return (
    <div className="bars">
      {items.map((item) => (
        <div key={item.name} style={{ display: "contents" }}>
          <span className="muted">{item.name}</span>
          <div className="track">
            <div className="fill" style={{
              width: `${Math.max(2, Math.min(100, item.value))}%`,
              background: item.value >= 60 ? "var(--blue)" : "var(--muted)",
            }} />
          </div>
          <span className="num" style={{ textAlign: "right" }}>{Math.round(item.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Tabs: one panel shown at a time, so long lists do not push the page down. */
export function Tabs({ tabs, active, onChange, label }: {
  tabs: { id: string; label: ReactNode; count?: number }[]; active: string;
  onChange: (id: string) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button key={tab.id} type="button" role="tab" id={`tab-${tab.id}`} aria-selected={tab.id === active}
          aria-controls={`panel-${tab.id}`} className={tab.id === active ? "on" : ""}
          onClick={() => onChange(tab.id)}>
          {tab.label}{tab.count !== undefined ? <span className="count">{tab.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

/** A panel that slides in from the right; Escape or the backdrop closes it. */
export function Drawer({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="drawer-wrap">
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Details"}>
        <div className="drawer-head">
          <h3>{title}</h3>
          <button type="button" className="small" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

/** One small number with its name, for a row of key figures. */
export function Stat({ name, value, note, tone }: { name: ReactNode; value: ReactNode; note?: ReactNode; tone?: string }) {
  return (
    <div className="stat">
      <span className="name">{name}</span>
      <span className={`value num ${tone ?? ""}`}>{value}</span>
      {note ? <span className="note">{note}</span> : null}
    </div>
  );
}
