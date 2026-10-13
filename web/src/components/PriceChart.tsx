// Candlestick chart (TradingView lightweight-charts) with the 20-day average and price lines.
import { useEffect, useRef } from "react";
import {
  ColorType, createChart, CrosshairMode, IChartApi, LineStyle, UTCTimestamp,
} from "lightweight-charts";
import { Bars } from "../api";

type Level = { price: number; title: string; color: string };

function css(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

const toTime = (text: string) => (Date.parse(text + "T00:00:00Z") / 1000) as UTCTimestamp;

export default function PriceChart({ data, levels, theme, height = 400 }: {
  data: Bars; levels: Level[]; theme: string; height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const up = css("--up"), down = css("--down");
    const chart = createChart(box.current, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css("--muted"),
        fontFamily: "IBM Plex Sans, system-ui, sans-serif" },
      grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
      rightPriceScale: { borderColor: css("--line") },
      timeScale: { borderColor: css("--line"), timeVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });
    chartRef.current = chart;
    const candles = chart.addCandlestickSeries({
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down,
      wickUpColor: up, wickDownColor: down,
    });
    candles.setData(data.bars.map((bar) => ({
      time: toTime(bar.time), open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    })));
    const ema = chart.addLineSeries({ color: css("--warn"), lineWidth: 2, priceLineVisible: false,
      lastValueVisible: false, crosshairMarkerVisible: false });
    ema.setData(data.ema.map((point) => ({ time: toTime(point.time), value: point.value })));
    const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume",
      lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(data.bars.map((bar) => ({
      time: toTime(bar.time), value: bar.volume,
      color: bar.close >= bar.open ? "rgba(76,195,138,0.35)" : "rgba(242,101,92,0.35)",
    })));
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.22 } });
    for (const level of levels) {
      candles.createPriceLine({ price: level.price, color: level.color, lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: level.title });
    }
    chart.timeScale().fitContent();
    return () => { chart.remove(); chartRef.current = null; };
  }, [data, levels, theme, height]);

  return <div ref={box} className="chart-box" style={{ height }}
    role="img" aria-label={`${data.symbol} price chart with the 20-day average`} />;
}

export function LineChart({ series, theme, height = 260, unit = "rupees", label = "Growth of the model against Nifty" }: {
  series: { name: string; color: string; points: { time: string; value: number }[] }[];
  theme: string; height?: number; unit?: "rupees" | "percent"; label?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!box.current) return;
    const chart = createChart(box.current, {
      height, autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css("--muted"),
        fontFamily: "IBM Plex Sans, system-ui, sans-serif" },
      grid: { vertLines: { visible: false }, horzLines: { color: css("--line") } },
      rightPriceScale: { borderColor: css("--line") },
      timeScale: { borderColor: css("--line") },
      localization: { priceFormatter: (value: number) => unit === "percent"
        ? `${Math.round(value)}%` : `₹${Math.round(value).toLocaleString("en-IN")}` },
    });
    for (const line of series) {
      const drawn = chart.addLineSeries({ color: line.color.startsWith("--") ? css(line.color) : line.color,
        lineWidth: 2, priceLineVisible: false, title: line.name });
      drawn.setData(line.points.map((point) => ({ time: toTime(point.time), value: point.value })));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [series, theme, height, unit]);
  return <div ref={box} style={{ height }} role="img" aria-label={label} />;
}
