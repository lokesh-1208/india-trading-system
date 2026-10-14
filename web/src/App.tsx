// The frame around every page: top bar, update progress, and the pages themselves.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { getJson, Job, postJson, Status, Strip } from "./api";
import { Logo } from "./components/ui";
import { pct, num } from "./format";
import TodayPage from "./pages/Today";
import MarketHub, { MARKET_TABS } from "./pages/MarketHub";
import StockPage from "./pages/Stock";
import TradesPage from "./pages/Trades";

type AppState = {
  version: number; theme: string; status: Status | null;
  startJob: (kind: string) => void; job: Job | null;
};
export const AppContext = createContext<AppState>({
  version: 0, theme: "dark", status: null, startJob: () => {}, job: null,
});
export const useApp = () => useContext(AppContext);

function savedTheme() {
  try { return localStorage.getItem("kasauti-theme") || "dark"; } catch { return "dark"; }
}

function StockSearch() {
  const [symbols, setSymbols] = useState<{ symbol: string; industry: string }[]>([]);
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  useEffect(() => { getJson<typeof symbols>("/api/stocks").then(setSymbols).catch(() => {}); }, []);
  const found = text.trim()
    ? symbols.filter((item) => item.symbol.includes(text.trim().toUpperCase())).slice(0, 12)
    : [];
  const go = (symbol: string) => { setText(""); setOpen(false); navigate(`/stocks/${symbol}`); };
  return (
    <div className="search">
      <label htmlFor="find" className="sr-only" style={{ position: "absolute", left: -9999 }}>Find a stock</label>
      <input id="find" type="search" placeholder="Find a stock" value={text} autoComplete="off"
        style={{ width: 170 }}
        onChange={(event) => { setText(event.target.value); setOpen(true); setActive(0); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { setActive((index) => Math.min(index + 1, found.length - 1)); event.preventDefault(); }
          if (event.key === "ArrowUp") { setActive((index) => Math.max(index - 1, 0)); event.preventDefault(); }
          if (event.key === "Enter" && found[active]) go(found[active].symbol);
          if (event.key === "Escape") setOpen(false);
        }} />
      {open && found.length ? (
        <ul role="listbox" aria-label="Matching stocks">
          {found.map((item, index) => (
            <li key={item.symbol} role="option" aria-selected={index === active}>
              <a href={`/stocks/${item.symbol}`} className={index === active ? "on" : ""}
                onClick={(event) => { event.preventDefault(); go(item.symbol); }}>
                <strong>{item.symbol}</strong><span className="small muted">{item.industry}</span>
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function JobBar({ job, onClose }: { job: Job | null; onClose: () => void }) {
  if (!job || (!job.running && !job.message && !job.error)) return null;
  const share = job.total ? Math.round((job.done / job.total) * 100) : 0;
  return (
    <div className="job" role="status" aria-live="polite">
      {job.running ? (
        <>
          <strong>{job.label}</strong>
          <span>{job.step}{job.total ? `: ${job.done} of ${job.total}` : ""}</span>
          <div className="progress" aria-hidden="true"><div style={{ width: `${share}%` }} /></div>
          <span className="muted">{job.seconds ?? 0} s</span>
        </>
      ) : (
        <>
          <strong>{job.error ? "The update stopped." : `${job.label}: finished.`}</strong>
          <span style={{ flex: 1 }}>{job.error || job.message}</span>
          <button className="small" onClick={onClose}>Close</button>
        </>
      )}
    </div>
  );
}

// Live Nifty, India VIX, dollar-rupee and Brent for the top bar, asked every minute.
function useLiveStrip() {
  const [strip, setStrip] = useState<(Strip & { time?: string })[] | null>(null);
  useEffect(() => {
    let stopped = false;
    const ask = () => {
      if (document.visibilityState === "hidden") return;
      getJson<(Strip & { time?: string })[]>("/api/live-indices")
        .then((found) => { if (!stopped && found.length) setStrip(found); }).catch(() => {});
    };
    ask();
    const timer = window.setInterval(ask, 60_000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, []);
  return strip;
}

export default function App() {
  const [theme, setTheme] = useState(savedTheme);
  const { pathname } = useLocation();
  const liveStrip = useLiveStrip();
  const [status, setStatus] = useState<Status | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [version, setVersion] = useState(0);
  const [jobSeen, setJobSeen] = useState<number | null>(null);
  const wasRunning = useRef(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("kasauti-theme", theme); } catch { /* private window */ }
  }, [theme]);

  const refreshStatus = useCallback(() => {
    getJson<Status>("/api/status").then((found) => { setStatus(found); setJob(found.job); }).catch(() => {});
  }, []);
  useEffect(refreshStatus, [refreshStatus, version]);

  // While an update runs, ask for its progress every second; reload the pages when it ends.
  useEffect(() => {
    if (!job?.running) return;
    wasRunning.current = true;
    const timer = setInterval(() => {
      getJson<Job>("/api/jobs").then((found) => {
        setJob(found);
        if (!found.running && wasRunning.current) {
          wasRunning.current = false;
          setVersion((value) => value + 1);
        }
      }).catch(() => {});
    }, 1000);
    return () => clearInterval(timer);
  }, [job?.running]);

  const startJob = useCallback((kind: string) => {
    postJson<Job>("/api/jobs", { kind }).then(setJob).catch((problem: Error) =>
      setJob({ running: false, kind, label: "Update", step: null, done: 0, total: 0,
        message: null, error: problem.message, finished: null }));
  }, []);

  const showJob = job && (job.running || (job.finished !== jobSeen && (job.message || job.error)));
  // Three places: act (Today), understand (Market), look things up and keep records (Stocks & trades).
  const marketPaths = MARKET_TABS.map(([path]) => path);
  const pages: [string, string, boolean][] = [
    ["/", "Today", pathname === "/"],
    ["/market", "Market", marketPaths.includes(pathname)],
    ["/trades", "Stocks & trades", pathname.startsWith("/trades") || pathname.startsWith("/stocks")],
  ];
  const strip = liveStrip ?? status?.strip ?? [];

  return (
    <AppContext.Provider value={{ version, theme, status, startJob, job }}>
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="Kasauti, Today"><Logo /><span>Kasauti</span></NavLink>
        <nav className="nav" aria-label="Pages">
          {pages.map(([path, label, active]) => (
            <NavLink key={label} to={path} end={path === "/"} className={active ? "active" : ""}
              aria-current={active ? "page" : undefined}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="strip">
          {strip.map((item) => (
            <div className="strip-item" key={item.name}>
              <span className="label">{item.name}{liveStrip ? <span className="live-dot" title="live" aria-label="live" /> : null}</span>
              <span className="value num">{num(item.value)}{" "}
                <span className={item.name === "India VIX" ? (item.change < 0 ? "up" : "down") : item.change >= 0 ? "up" : "down"}>
                  {pct(item.change, 2)}
                </span>
              </span>
            </div>
          ))}
          <StockSearch />
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Switch light or dark">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </header>
      {showJob ? <JobBar job={job} onClose={() => setJobSeen(job?.finished ?? null)} /> : null}
      <main className="page">
        <Routes>
          <Route path="/" element={<TodayPage />} />
          {marketPaths.map((path) => <Route key={path} path={path} element={<MarketHub />} />)}
          <Route path="/stocks/:symbol" element={<StockPage />} />
          <Route path="/trades" element={<TradesPage />} />
          <Route path="*" element={<TodayPage />} />
        </Routes>
      </main>
    </AppContext.Provider>
  );
}
