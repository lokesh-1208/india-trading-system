// Talking to the local Python server. Every page asks one address and gets plain data back.
import { useCallback, useEffect, useState } from "react";

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `${response.status} ${response.statusText}`);
  return data as T;
}

/** Load one address; reload when `version` changes (after an update finishes). */
export function useApi<T>(path: string | null, version = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    if (!path) return;
    setLoading(true);
    getJson<T>(path)
      .then((found) => { setData(found); setError(null); })
      .catch((problem: Error) => setError(problem.message))
      .finally(() => setLoading(false));
  }, [path]);
  useEffect(load, [load, version]);
  return { data, error, loading, reload: load, setData };
}

// ---- shapes of the answers ----
export type LivePrice = { price: number; previous_close: number | null; "change_%": number | null; time: string | null };
export type Live = { time: string; market_open: boolean; prices: Record<string, LivePrice> };
export type Ladder = { stop: number; signal: number; limit: number; last: number; low: number; high: number };
export type BuyItem = {
  symbol: string; rank: number; score: number; about: string; ladder: Ladder; shares: number;
  amount: number; kind: string; status: string; tag?: string; why?: string; size_share?: number;
};
export type MoneyPlan = {
  capital: number; account: number; cash: number; invested: number; holdings_value: number;
  per_stock: number; share: number; places: number; spend: number; cash_after: number;
  open_places_after: number; reserve: number; idle: number; note: string; warning?: string | null;
  buys: { symbol: string; shares: number; limit: number; amount: number }[];
};
export type SectorStock = BuyItem & { group: "top" | "sector" };
export type Sector = { industry: string; in_top: number; stocks: SectorStock[] };
export type WeekRow = {
  symbol: string; rank: number; score: number; status: string; why: string; close: number; limit: number;
  last: number; ranks: Record<string, number>; "since_first_%": number | null; "nifty_%": number | null;
};
export type Holding = {
  symbol: string; action: "HOLD" | "SELL" | "WAIT"; reason: string; quantity: number; buy_price: number; weakest?: boolean;
  size_vs_plan?: number | null; peak?: number | null; trail_from?: number | null; trail_active?: boolean;
  last_price: number; "gain_%": number | null; gain_rs: number | null; stop_loss: number;
  trend_line: number | null; bought: string; days_held: number; exit_line: number; exit_pct: number;
  exit_rs: number; gtt: number; warning?: boolean; industry?: string;
};
export type Today = {
  list_day: string; signal_day: string; week_of: string; headline: string; nothing_to_sell: boolean;
  explain: string; money_plan: MoneyPlan; buy_window?: { open: boolean; day: string | null; next: string }; list_from: string | null; next_list: string; week_list: WeekRow[]; week_days: string[];
  sectors?: Sector[]; sector_rules?: { per_sector: number; min_score: number };
  market: {
    level: string; note: string; ok: boolean; share: number; per_stock: number; money: number;
    positions: number; checks_pass: number; checks_total: number; checks_unknown: string[]; stop_loss: number; max_gap: number;
  };
  buys: BuyItem[]; holds: Holding[]; skips: BuyItem[];
  watch: { symbol: string; rank: number; score: number; close: number }[];
  avoid: { symbol: string; score: number; price: number }[];
  tracker: { days: string[]; rows: TrackerRow[] };
  results_due: { symbol: string; date: string }[];
};
export type TrackerRow = {
  symbol: string; ranks: Record<string, number>; days_on: number; last_week: boolean; on_today: boolean;
  first_day: string; "since_first_%": number | null; "nifty_%": number | null; vs_nifty: number | null;
};
export type Strip = { name: string; value: number; change: number };
export type Job = {
  running: boolean; kind: string | null; label: string | null; step: string | null; done: number;
  total: number; message: string | null; error: string | null; seconds?: number; finished: number | null;
};
export type Status = {
  prices_to: string; fresh: boolean; text: string; updated: string | null; strip: Strip[]; now: string; job: Job;
  missed_flow_days?: string[];
};
export type Likely = {
  symbol: string; direction: number; strength: number; reasons: string[]; open_pct: number | null;
  link: string; industry: string; yours: "held" | "weekly" | null; view: string; rank: number | null;
};
export type BeforeOpen = {
  since: string; guess: string; reasons: string[]; sectors: string[]; preopen_ready: boolean;
  moves: { name: string; market: string; "change_%": number; day: string }[];
  up: Likely[]; down: Likely[]; note: string; stage?: "before" | "open" | "after" | "closed";
};
export type Idea = {
  symbol: string; time: string; label: string; lean: number; what: string; link: string;
  "move_since_%": number | null; rank: number | null; score: number | null; view: string;
  history: string; idea: string; agree: string;
};
export type NewsIdeas = {
  buys: Idea[]; exits: Idea[]; days: number; note: string;
  reactions: { group: string; lean: number; cases: number; "average_%": number; "beat_nifty_%": number }[];
};
export type Mover = {
  symbol: string; day: string; close: number; "change_%": number; "gap_%": number; volume_x: number;
  turnover_cr: number; why: string; link: string; industry: string;
};
export type Movers = {
  day: string | null; mood: { label: string; text: string; rushing_in: number; rushing_out: number } | null;
  up: Mover[]; down: Mover[]; rule: { move: number; volume: number };
};
export type Market = {
  level: string; note: string; checks_day?: string;
  checks: { name: string; passed: boolean | null; detail?: string | null }[];
  markets: { name: string; value: number; change: number; day?: string }[];
  avoid: { symbol: string; score: number; price: number }[];
  fii_dii: { date: string; FII: number | null; DII: number | null }[];
  breadth: null | {
    day: string; above_20: number; above_20_week_ago: number; above_200: number; above_200_week_ago: number;
    series: { time: string; above_20: number; above_200: number }[];
  };
  sectors: { industry: string; stocks: number; "month_%": number; "above_ema_%": number; score: number }[];
  history: {
    summary: Record<string, number | string>;
    by_year: { year: number; model: number; nifty: number }[];
    equity: { time: string; model: number; nifty: number }[];
  };
};
export type StockPage = {
  symbol: string; industry: string; price: number; change: number; change_pct: number; as_of: string;
  stands: { kind: string; text: string }[];
  levels: { bought?: number; stop?: number; limit?: number };
  trend_line: number;
  model: null | {
    score: number; rank: number; of: number; view: string;
    groups: { name: string; value: number }[]; checks: { name: string; passed: boolean }[];
  };
  next_results: string | null;
  card: Record<string, number | string | null>;
  financial: boolean;
  scorecard: { passed: number; total: number; checks: { name: string; passed: boolean | null }[] };
  pledged_pct: number | null; pledge_red_flag: number;
  owners: null | {
    quarter: string; pledged: boolean | null;
    groups: { name: string; value: number | null; change: number | null }[];
    funds: { name: string; percent: number }[];
  };
  news: { time: string; type: string; what: string; link: string }[];
  deals: { date: string; kind: string; client: string; side: string; quantity: number; price: number }[];
  calls: { time: string; what: string; link: string }[];
  peers: { symbol: string; rank: number; score: number; price: number }[];
};
export type Bars = {
  symbol: string;
  bars: { time: string; open: number; high: number; low: number; close: number; volume: number }[];
  ema: { time: string; value: number }[];
};
export type Trades = {
  totals: {
    open_count: number; invested: number; value: number; open_gain: number; closed_count: number;
    closed_profit: number; closed_charges: number; closed_net: number; tax_estimate: number;
  };
  open: {
    row: number; symbol: string; buy_date: string; buy_price: number; quantity: number; cost: number;
    last_price: number; value: number; gain: number; "gain_%": number; note: string;
  }[];
  closed: {
    row: number; symbol: string; buy_date: string; buy_price: number; quantity: number; sell_date: string;
    sell_price: number; profit: number; "profit_%": number; charges: number; net_profit: number;
  }[];
  symbols: string[];
};
