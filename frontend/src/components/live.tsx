// Live prices: asked again every minute while the page is open (and visible).
// They only show where a stock is now; buy, hold and sell decisions come from the close.
import { useEffect, useState } from "react";
import { getJson, Live, LivePrice } from "../api";
import { pct, price } from "../format";

export const LIVE_EVERY_MS = 60_000;

export function useLive(symbols: string[]) {
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
    const back = () => { if (document.visibilityState === "visible") ask(); };
    document.addEventListener("visibilitychange", back);
    return () => { stopped = true; window.clearInterval(timer); document.removeEventListener("visibilitychange", back); };
  }, [key]);
  return { live, failed };
}

export function clock(value: string | null | undefined) {
  if (!value) return "";
  return value.slice(11, 16);
}

export function LiveNote({ quote }: { quote?: LivePrice }) {
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
