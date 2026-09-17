// Phase 15 — dependency-free SVG chart primitives for the control center.
// Charts accept data through props and render REAL backend values only.
// They animate once on mount (700–1000ms ease-out) using the design-system
// classes from index.css (.donut-track / .gauge-track / .bar-grow /
// .chart-in) and respect prefers-reduced-motion globally.

import { useEffect, useId, useMemo, useState } from 'react';

/* Fixed palette mirrors the CSS tokens in index.css (never invented data). */
export const CHART_COLORS = {
  pass: '#22C55E',
  fail: '#EF4444',
  error: '#F59E0B',
  skip: '#64748B',
  cyan: '#22D3EE',
  blue: '#3B82F6',
  purple: '#8B5CF6',
  track: '#1A263B',
  grid: '#243244',
  gridSoft: 'rgba(36, 50, 68, 0.6)',
  text: '#94A3B8',
};

function GradDef({ id, from, to, x1 = '0%', y1 = '0%', x2 = '100%', y2 = '100%' }) {
  return (
    <defs>
      <linearGradient id={id} x1={x1} y1={y1} x2={x2} y2={y2}>
        <stop offset="0%" stopColor={from} />
        <stop offset="100%" stopColor={to} />
      </linearGradient>
    </defs>
  );
}

function polar(cx, cy, r, angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}

function describeArc(cx, cy, r, startDeg, endDeg) {
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const largeArc = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x.toFixed(3)} ${start.y.toFixed(3)} A ${r} ${r} 0 ${largeArc} 1 ${end.x.toFixed(3)} ${end.y.toFixed(3)} Z`;
}

/* Number → "1.2k / 3.4m" style abbreviations (only for axis labels). */
function fmtAxis(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(n));
}

// Build a clean axis maximum from a "nice" 1-2-5 step, so gridlines land on
// round numbers regardless of data magnitude.
function niceMax(values, targetTicks = 4) {
  const rawMax = Math.max(1, ...values.map((v) => Number(v) || 0));
  const rough = rawMax / targetTicks;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const stepPow = rough / pow;
  const step = (stepPow >= 5 ? 5 : stepPow >= 2 ? 2 : 1) * pow;
  return Math.ceil(rawMax / step) * step;
}

// ---------------------------------------------------------------------------
// 1. DonutChart — concentric status split (PASS / FAIL / ERROR / SKIPPED).
//    Segments draw in with an 80ms stagger over ~900ms.
export function DonutChart({
  segments,
  size = 168,
  thickness = 20,
  centerLabel,
  centerSub,
  centerHint,
}) {
  const uid = useId().replace(/:/g, '');
  const [done, setDone] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDone(true), 60);
    return () => clearTimeout(t);
  }, []);

  const total = segments.reduce((sum, s) => sum + (Number(s.value) || 0), 0);
  const r = (size - thickness) / 2;
  const C = 2 * Math.PI * r;
  const cx = size / 2;
  const cy = size / 2;

  if (total <= 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-card border border-line bg-bg-secondary/40 text-xs text-ink-disabled"
        style={{ width: size, height: size }}
        role="img"
        aria-label="No chart data available"
      >
        No data
      </div>
    );
  }

  const summary = segments
    .filter((s) => Number(s.value) > 0)
    .map((s) => `${s.label}: ${s.value}`)
    .join(', ');

  let acc = 0;
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={centerLabel ? `${centerLabel} — ${summary}` : `Donut chart — ${summary}`}
      >
        <title>{summary || 'No data'}</title>
        <GradDef id={`don-${uid}`} from="#22D3EE" to="#3B82F6" />
        {/* Soft outer ambient ring */}
        <circle cx={cx} cy={cy} r={r + thickness / 2 + 2} fill="none" stroke="rgba(34, 211, 238, 0.05)" strokeWidth={1} />
        {/* Track */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={CHART_COLORS.track} strokeWidth={thickness} />
        {segments.map((s, i) => {
          const frac = (Number(s.value) || 0) / total;
          if (frac <= 0) return null;
          const dash = frac * C;
          const offset = acc * C;
          acc += frac;
          const drawn = done ? dash : 0;
          return (
            <circle
              key={s.label}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={s.color || CHART_COLORS.cyan}
              strokeWidth={thickness}
              strokeDasharray={`${drawn} ${C - drawn}`}
              strokeDashoffset={-offset}
              className="donut-track tab-nums"
              transform={`rotate(-90 ${cx} ${cy})`}
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <title>{`${s.label}: ${s.value}`}</title>
            </circle>
          );
        })}
      </svg>
      <div className="pointer-events-none absolute flex flex-col items-center px-2 text-center">
        <div className="tab-nums text-2xl font-bold leading-none text-ink">{centerLabel}</div>
        {centerSub ? <div className="mt-1 text-[11px] text-ink-muted">{centerSub}</div> : null}
        {centerHint ? <div className="mt-0.5 text-[10px] uppercase tracking-wider text-ink-disabled">{centerHint}</div> : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. GaugeChart — 270° engineering gauge for percentage metrics.
//    Includes major/minor ticks and a glowing tip dot that settles on the
//    animated value. Value arc animates over 900ms (d-transition).
export function GaugeChart({
  value,
  size = 172,
  centerLabel,
  sub,
  from = '#22D3EE',
  to = '#3B82F6',
  showTicks = true,
}) {
  const uid = useId().replace(/:/g, '');
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const [done, setDone] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDone(true), 60);
    return () => clearTimeout(t);
  }, [value]);

  const cx = size / 2;
  const cy = size - 8;
  const r = cx - 12;
  const start = 135;
  const span = 270;
  const valueEnd = start + (span * (done ? v : 0)) / 100;

  const ticks = useMemo(() => {
    const out = [];
    for (let t = 0; t <= 100; t += 5) {
      const a = start + (span * t) / 100;
      const major = t % 20 === 0;
      const p1 = polar(cx, cy, r - 14, a);
      const p2 = polar(cx, cy, r - (major ? 20 : 17.5), a);
      out.push({ p1, p2, major });
    }
    return out;
  }, [cx, cy, r, size]);

  const tip = polar(cx, cy, r - 7, valueEnd);

  return (
    <div className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={
          centerLabel
            ? `${centerLabel}: ${v.toFixed(0)} percent${sub ? ` (${sub})` : ''}`
            : `Gauge: ${v.toFixed(0)} percent`
        }
      >
        <title>{`${centerLabel || 'Value'}: ${v.toFixed(0)}%`}</title>
        <GradDef id={`g-${uid}`} from={from} to={to} />

        {/* Filled arc background */}
        <path d={describeArc(cx, cy, r, start, start + span)} fill="rgba(26, 38, 59, 0.6)" stroke={CHART_COLORS.grid} strokeWidth="1.5" />

        {/* Value track */}
        <path d={describeArc(cx, cy, r - 7, start, start + span)} fill="none" stroke={CHART_COLORS.track} strokeWidth="10" strokeLinecap="round" />

        {/* Animated value arc */}
        <path
          d={describeArc(cx, cy, r - 7, start, valueEnd)}
          fill="none"
          stroke={`url(#g-${uid})`}
          strokeWidth="10"
          strokeLinecap="round"
          style={{ transition: 'd 900ms cubic-bezier(0.4, 0, 0.2, 1)' }}
        />

        {/* Major / minor ticks along the inner rim */}
        {showTicks &&
          ticks.map((t) => (
            <line
              key={`${t.major}-${t.p1.x.toFixed(1)}-${t.p1.y.toFixed(1)}`}
              x1={t.p1.x}
              y1={t.p1.y}
              x2={t.p2.x}
              y2={t.p2.y}
              stroke={CHART_COLORS.gridSoft}
              strokeWidth={t.major ? 2 : 1}
              strokeLinecap="round"
            />
          ))}

        {/* Settling tip dot */}
        <circle
          cx={tip.x}
          cy={tip.y}
          r={4.5}
          fill={`url(#g-${uid})`}
          stroke="#0B1120"
          strokeWidth="2"
          className={done ? 'opacity-100' : 'opacity-0'}
          style={{ transition: 'opacity 400ms ease-out 800ms' }}
        />
      </svg>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center pt-2">
        <div className="tab-nums text-[64px] font-bold leading-none tracking-tight">
          <span className="text-gradient" style={{ backgroundImage: `linear-gradient(90deg, ${from}, ${to})` }}>
            {v.toFixed(0)}
          </span>
          <span className="text-2xl text-ink-muted">%</span>
        </div>
        {centerLabel ? (
          <div className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{centerLabel}</div>
        ) : null}
        {sub ? <div className="mt-0.5 text-[11px] text-ink-muted">{sub}</div> : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. BarChart — grouped vertical bars with a clean y-axis grid. Responsive:
//    the SVG scales to its container; if `minWidth` causes overflow the
//    wrapper scrolls. Bars grow in with a 60ms stagger over ~850ms.
export function BarChart({
  data,
  height = 180,
  max,
  unit = '',
  minWidth,
  baselineLabel = true,
  ariaLabel = 'Bar chart',
}) {
  const items = data || [];
  const yMax = max ?? niceMax(items.map((d) => Number(d.value) || 0));
  const ticks = Array.from({ length: 5 }, (_, i) => (i / 4) * yMax);
  const W = 420;
  const H = 160;
  const padL = 40;
  const padB = 26;
  const padT = 14;
  const plotW = W - padL - 12;
  const plotH = H - padT - padB;
  const n = Math.max(1, items.length);
  const slot = plotW / n;
  const barW = Math.min(54, slot * 0.56);

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-card border border-line bg-bg-secondary/40 text-xs text-ink-disabled" style={{ height }}>
        No data
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto" style={{ minWidth }}>
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={ariaLabel}
        style={{ minWidth: minWidth || undefined }}
      >
        <title>{items.map((d) => `${d.label}: ${d.value}`).join(', ')}</title>
        <GradDef id="bc-cyan" from="#22D3EE" to="#3B82F6" />
        <GradDef id="bc-blue" from="#3B82F6" to="#8B5CF6" />
        <GradDef id="bc-green" from="#22C55E" to="#16A34A" />

        {/* Y gridlines + labels */}
        {ticks.map((t) => {
          const y = padT + plotH - (t / yMax) * plotH;
          return (
            <g key={t}>
              <line x1={padL} y1={y} x2={W - 8} y2={y} stroke={CHART_COLORS.gridSoft} strokeWidth="1" strokeDasharray={t === 0 ? '0' : '2 4'} />
              <text x={padL - 6} y={y + 3.5} textAnchor="end" fontSize="9" fill={CHART_COLORS.text} className="tab-nums">
                {fmtAxis(t)}
                {t === yMax && unit ? unit : ''}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {items.map((d, i) => {
          const val = Math.max(0, Number(d.value) || 0);
          const h = (val / yMax) * plotH;
          const x = padL + i * slot + (slot - barW) / 2;
          const y = padT + plotH - h;
          const fill =
            d.gradient || (d.color === CHART_COLORS.cyan ? 'url(#bc-cyan)' : d.color === CHART_COLORS.blue ? 'url(#bc-blue)' : d.color === CHART_COLORS.pass ? 'url(#bc-green)' : d.color);
          return (
            <g key={d.label}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(h, 1)}
                rx={4}
                fill={fill}
                className="bar-grow"
                style={{ transformOrigin: `${x + barW / 2}px ${padT + plotH}px`, animationDelay: `${i * 60}ms` }}
              >
                <title>{`${d.label}: ${d.value}${unit}`}</title>
              </rect>
              <text
                x={x + barW / 2}
                y={padT + plotH + 14}
                textAnchor="middle"
                fontSize="9"
                fill={CHART_COLORS.text}
                className="tab-nums"
              >
                {d.label}
              </text>
              {val > 0 && (
                <text
                  x={x + barW / 2}
                  y={Math.max(y - 4, padT + 8)}
                  textAnchor="middle"
                  fontSize="9"
                  fontWeight="600"
                  fill="#CBD5E1"
                  className="tab-nums"
                >
                  {fmtAxis(val)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SegmentedBars — compact vertical bars (execution history / iterations).
// Kept for back-compat; thinner and lighter than BarChart, great for cards.
export function SegmentedBars({ items, height = 120, hint, ariaLabel = 'Segmented bar chart' }) {
  const max = Math.max(1, ...items.map((i) => Number(i.value) || 0));
  if (!items.length) return null;
  return (
    <div>
      <div className="flex items-end justify-between gap-2" style={{ height }} role="img" aria-label={ariaLabel}>
        {items.map((i, idx) => {
          const val = Number(i.value) || 0;
          return (
            <div key={i.label} className="group flex h-full flex-1 flex-col items-center justify-end gap-1.5" title={`${i.label}: ${val}`}>
              <div className="tab-nums font-mono text-[10px] text-ink-muted opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                {i.value}
              </div>
              <div
                className="bar-grow w-full max-w-[46px] rounded-t-md"
                style={{
                  height: `${(val / max) * 100}%`,
                  minHeight: val > 0 ? 4 : 0,
                  background: i.gradient || i.color,
                  animationDelay: `${idx * 60}ms`,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between gap-2">
        {items.map((i) => (
          <div key={i.label} className="flex-1 truncate text-center text-[10px] text-ink-muted" title={i.label}>
            {i.label}
          </div>
        ))}
      </div>
      {hint ? <div className="mt-2 text-[10px] text-ink-disabled">{hint}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StackedBar — single horizontal bar split into segments (PASS/FAIL/...).
export function StackedBar({ segments, h = 12, gradient = false }) {
  const total = segments.reduce((s, x) => s + (Number(x.value) || 0), 0);
  if (total <= 0) return null;

  let cumulative = 0;
  return (
    <div
      className="flex w-full overflow-hidden rounded-pill border border-line/40 bg-bg-secondary"
      style={{ height: h * 4 }}
      role="img"
      aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(', ')}
    >
      {segments.map((s) => {
        const val = Number(s.value) || 0;
        if (val <= 0) return null;
        cumulative += val;
        const isLast = cumulative >= total;
        return (
          <div
            key={s.label}
            title={`${s.label}: ${s.value}`}
            style={{
              width: `${((val / total) * 100).toFixed(2)}%`,
              background: gradient && s.gradient ? s.gradient : s.color,
              borderTopRightRadius: isLast ? 4 : 0,
              borderBottomRightRadius: isLast ? 4 : 0,
              transition: 'width 800ms ease-out',
            }}
          />
        );
      })}
    </div>
  );
}