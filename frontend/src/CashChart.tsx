import { useId, useMemo, useRef, useState } from "react";
import { cny, cnyShort } from "./format";

export type DailyRow = { day: number; date: string; closing_minor: number; inflow_minor: number; outflow_minor: number; event_refs: string[] };
export type Series = { key: string; label: string; daily: DailyRow[]; color: "primary" | "compare" };

const W = 760, H = 300, M = { top: 18, right: 24, bottom: 34, left: 64 };

export function CashChart({ series, bufferMinor, title }: { series: Series[]; bufferMinor: number; title: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/:/g, "");
  const days = series[0]?.daily.length ?? 0;

  const { yMin, yMax, ticks } = useMemo(() => {
    const vals = series.flatMap((s) => s.daily.map((d) => d.closing_minor)).concat([bufferMinor, 0]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const step = niceStep((hi - lo) / 5);
    const rawLo = lo;
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    if (rawLo < 0 && rawLo - lo < step * 0.6) lo -= step; // headroom under the lowest point for its label
    const t: number[] = [];
    for (let v = lo; v <= hi + 1; v += step) t.push(v);
    return { yMin: lo, yMax: hi, ticks: t };
  }, [series, bufferMinor]);

  if (!days) return null;
  const x = (d: number) => M.left + (d / days) * (W - M.left - M.right);
  const y = (v: number) => M.top + ((yMax - v) / (yMax - yMin || 1)) * (H - M.top - M.bottom);
  // Step-after path: each end-of-day balance holds until the next day.
  const path = (rows: DailyRow[]) =>
    rows.map((r, i) => (i === 0 ? `M${x(r.day).toFixed(1)},${y(r.closing_minor).toFixed(1)}` : `V${y(r.closing_minor).toFixed(1)}`) + `H${x(r.day + 1).toFixed(1)}`).join("");
  const xTicks = [0, 3, 7, 10, 14, 21, 30, 46].filter((d) => d < days);
  // The shortfall: where the main series sits below zero. Fill the space between the line and zero.
  const main = series[0].daily;
  const low = main.reduce((a, r) => (r.closing_minor < a.closing_minor ? r : a), main[0]);
  const hasGap = low.closing_minor < 0;
  const gapPath = hasGap ? `${path(main)}V${y(0).toFixed(1)}H${x(main[0].day).toFixed(1)}Z` : "";
  const negDays = main.filter((r) => r.closing_minor < 0).length;
  const lowX = x(low.day + 0.5), lowY = y(low.closing_minor);
  const lowRight = lowX < W * 0.6;

  const onMove = (e: React.PointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const d = Math.floor(((px - M.left) / (W - M.left - M.right)) * days);
    setHover(d >= 0 && d < days ? d : null);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") { setHover((h) => Math.min(days - 1, (h ?? -1) + 1)); e.preventDefault(); }
    if (e.key === "ArrowLeft") { setHover((h) => Math.max(0, (h ?? 1) - 1)); e.preventDefault(); }
    if (e.key === "Escape") setHover(null);
  };
  const h = hover !== null ? series.map((s) => ({ s, row: s.daily[hover] })) : [];
  const tipLeft = hover !== null && x(hover) > W * 0.62;

  return (
    <figure className="viz-root chart">
      <figcaption>
        <span className="chart-title">{title}</span>
        <span className="legend" aria-hidden={series.length < 2}>
          {series.length > 1 && series.map((s) => (
            <span key={s.key} className="legend-item"><span className={`swatch ${s.color}`} />{s.label}</span>
          ))}
          <span className="legend-item"><span className="swatch buffer" />Owner buffer {cny(bufferMinor)}</span>
          {hasGap && <span className="legend-item"><span className="swatch gap" />Below zero for {negDays} days</span>}
        </span>
        <button className="link-btn" onClick={() => setShowTable((v) => !v)} aria-expanded={showTable}>{showTable ? "Hide table" : "Show daily table"}</button>
      </figcaption>
      <div className="chart-wrap">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0}
             aria-label={`${title}. Use left and right arrow keys to read daily closing balances.`}
             onPointerMove={onMove} onPointerLeave={() => setHover(null)} onKeyDown={onKey} onBlur={() => setHover(null)}>
          <defs>
            <pattern id={`gap-hatch-${uid}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" className="gap-hatch-line" />
            </pattern>
            <clipPath id={`below-zero-${uid}`}><rect x={M.left} y={y(0)} width={W - M.left - M.right} height={Math.max(0, H - M.bottom - y(0))} /></clipPath>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className={t === 0 ? "zero-line" : "grid"} />
              <text x={M.left - 8} y={y(t) + 4} textAnchor="end" className="axis-label">{cnyShort(t)}</text>
            </g>
          ))}
          {xTicks.map((d) => (
            <text key={d} x={x(d) + 2} y={H - 12} className="axis-label" textAnchor="start">d{d}</text>
          ))}
          <line x1={M.left} x2={W - M.right} y1={y(bufferMinor)} y2={y(bufferMinor)} className="buffer-line" />
          <text x={M.left + 4} y={y(bufferMinor) - 6} textAnchor="start" className="axis-label buffer-label">buffer</text>
          {hasGap && <path d={gapPath} className="gap-fill" style={{ fill: `url(#gap-hatch-${uid})` }} clipPath={`url(#below-zero-${uid})`} />}
          {[...series].reverse().map((s) => <path key={s.key} d={path(s.daily)} className={`series ${s.color}`} />)}
          {low.closing_minor < bufferMinor && (
            <g className="low-mark">
              <circle cx={lowX} cy={lowY} r={5} className="low-dot" />
              <text x={lowX + (lowRight ? -6 : 6)} y={lowY + 20} textAnchor={lowRight ? "start" : "end"} className="low-label">
                Lowest {cny(low.closing_minor)}<tspan className="low-sub" dx="8">day {low.day}, {low.date}</tspan>
              </text>
            </g>
          )}
          {hover !== null && (
            <g>
              <line x1={x(hover + 0.5)} x2={x(hover + 0.5)} y1={M.top} y2={H - M.bottom} className="crosshair" />
              {h.map(({ s, row }) => <circle key={s.key} cx={x(hover + 0.5)} cy={y(row.closing_minor)} r={4.5} className={`dot ${s.color}`} />)}
            </g>
          )}
        </svg>
        {hover !== null && (
          <div className="tooltip" style={{ left: `${(x(hover + 0.5) / W) * 100}%`, transform: tipLeft ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }} role="status">
            <div className="tip-head">Day {hover} · {series[0].daily[hover].date}</div>
            {h.map(({ s, row }) => (
              <div key={s.key} className="tip-row">
                {series.length > 1 && <span className={`swatch ${s.color}`} />}<span>{s.label}</span>
                <strong className={row.closing_minor < 0 ? "neg" : ""}>{cny(row.closing_minor)}</strong>
              </div>
            ))}
            {h[0]?.row.event_refs.length > 0 && <div className="tip-refs">Events: {h[0].row.event_refs.join(", ")}</div>}
          </div>
        )}
      </div>
      {showTable && (
        <div className="table-scroll">
          <table className="data">
            <caption className="sr-only">{title} daily balances</caption>
            <thead><tr><th>Day</th><th>Date</th>{series.map((s) => <th key={s.key} className="num">{s.label}</th>)}<th>Events ({series[0].label})</th></tr></thead>
            <tbody>
              {series[0].daily.map((r, i) => (
                <tr key={r.day} className={r.event_refs.length ? "" : "quiet"}>
                  <td>{r.day}</td><td>{r.date}</td>
                  {series.map((s) => <td key={s.key} className={`num ${s.daily[i].closing_minor < 0 ? "neg" : ""}`}>{cny(s.daily[i].closing_minor)}</td>)}
                  <td>{r.event_refs.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}

function niceStep(raw: number) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1))));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}
