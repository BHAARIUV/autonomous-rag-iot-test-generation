// Phase 15 — reusable UI primitives for the EXACT VISUAL DESIGN SYSTEM.
// Dependency-free primitives styled with Tailwind v4 tokens defined in
// `index.css`. Everything renders on the dark control-center palette.

import { useEffect, useState } from 'react';
import { isNA, fmtNum, fmtPct } from '../data.js';

// Maps a status string to a semantic tone used for badges and dots.
export function statusTone(status) {
  const s = isNA(status) ? 'Not available' : String(status);
  const normalized = s.toUpperCase();
  if (
    normalized.includes('PASS') ||
    normalized === 'COMPLETE' ||
    normalized === 'DETECTED' ||
    normalized === 'INJECTED' ||
    normalized === 'COVERED' ||
    normalized === 'VALIDATED' ||
    normalized === 'TARGET_REACHED' ||
    normalized === 'ONLINE' ||
    normalized.includes('INDEXED')
  ) {
    return 'ok';
  }
  if (
    normalized === 'FAIL' ||
    normalized.includes('FAIL') ||
    normalized === 'MISSED' ||
    normalized === 'UNCOVERED' ||
    normalized === 'REJECTED' ||
    normalized === 'ERROR' ||
    normalized.includes('OFFLINE')
  ) {
    return 'bad';
  }
  if (normalized === 'SKIPPED' || normalized === 'PENDING' || normalized === 'NOT_EXECUTED') {
    return 'skip';
  }
  if (normalized.includes('PARTIALLY') || normalized.includes('IN_PROGRESS') || normalized.includes('WARNING')) {
    return 'warn';
  }
  return 'na';
}

const BADGE_TONE = {
  ok: 'border-line-success bg-ok-bg text-green',
  warn: 'border-line-warn bg-warn-bg text-amber',
  bad: 'border-line-error bg-err-bg text-red',
  skip: 'border-line bg-bg-secondary text-ink-muted',
  na: 'border-line bg-bg-secondary text-ink-disabled',
};

export function Badge({ status }) {
  const s = isNA(status) ? 'Not available' : String(status);
  const tone = BADGE_TONE[statusTone(status)] || BADGE_TONE.na;
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold leading-5 ${tone}`}
    >
      <span className="h-1 w-1 rounded-full bg-current" />
      {s}
    </span>
  );
}

// Semantic accent gradients (only for important/categorical UI).
const ACCENT = {
  primary: 'from-cyan to-blue',
  cyan: 'from-cyan to-blue',
  blue: 'from-blue to-purple',
  green: 'from-green to-green',
  red: 'from-red to-red',
  purple: 'from-purple to-purple',
  amber: 'from-amber to-amber',
  fault: 'from-amber to-red',
  ai: 'from-blue to-purple',
  refine: 'from-cyan to-purple',
  slate: 'from-ink-muted to-ink-disabled',
};

// Icon chip text color: dark on bright cyan/blue gradients, white elsewhere.
const CHIP_DARK = new Set(['primary', 'cyan', 'refine', 'blue', 'ai']);

function chipClasses(accent, iconDark) {
  const g = ACCENT[accent] || ACCENT.primary;
  const dark = iconDark || CHIP_DARK.has(accent);
  return `bg-gradient-to-br ${g} ${dark ? 'text-bg-main' : 'text-white'}`;
}

function valueClasses(accent, na) {
  const g = ACCENT[accent] || ACCENT.primary;
  return na ? 'text-ink-disabled' : `text-gradient bg-gradient-to-r ${g}`;
}

// Internal card shell shared by Metric / MetricPct / cards.
function KpiShell({ label, value, suffix, accent, icon: Icon, delay, sub }) {
  const na = isNA(value);
  const display = na ? '—' : `${fmtNum(value)}${suffix}`;
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-20 w-20 rounded-full bg-gradient-to-br from-white/[0.04] to-transparent" />
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          {label}
        </div>
        {Icon && (
          <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${chipClasses(accent)}`}>
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
      </div>
      <div className={`text-3xl font-bold leading-tight ${valueClasses(accent, na)}`}>
        {display}
      </div>
      {sub ? <div className="mt-1 text-[11px] text-ink-muted">{sub}</div> : null}
    </div>
  );
}

export function Metric({ label, value, na = false, accent = 'primary', suffix = '', icon, delay, sub }) {
  return (
    <KpiShell
      label={label}
      value={na ? 'Not available' : value}
      accent={accent}
      suffix={suffix}
      icon={icon}
      delay={delay}
      sub={sub}
    />
  );
}

export function MetricPct({ label, value, accent = 'primary', icon: Icon, delay, sub }) {
  const display = isNA(value) ? '—' : fmtPct(value);
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-20 w-20 rounded-full bg-gradient-to-br from-white/[0.04] to-transparent" />
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          {label}
        </div>
        {Icon && (
          <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${chipClasses(accent)}`}>
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
      </div>
      <div className={`text-3xl font-bold leading-tight ${valueClasses(accent, isNA(value))}`}>
        {display}
      </div>
      {sub ? <div className="mt-1 text-[11px] text-ink-muted">{sub}</div> : null}
    </div>
  );
}

export function Section({ id, title, lede, icon: Icon, right, children, delay = 0, pad = 'p-5' }) {
  return (
    <section
      id={id}
      className="anim-entry overflow-hidden rounded-panel border border-line bg-card shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line/70 px-5 py-4">
        <div className="flex items-center gap-3">
          {Icon && (
            <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-blue text-white shadow-ai">
              <Icon size={16} strokeWidth={2} />
            </span>
          )}
          <div>
            <h3 className="text-lg font-semibold leading-tight text-ink">{title}</h3>
            {lede ? <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{lede}</p> : null}
          </div>
        </div>
        {right}
      </header>
      <div className={pad}>{children}</div>
    </section>
  );
}

export function StatCards({ items, cols = 'xl:grid-cols-5' }) {
  return (
    <div className={`mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 ${cols}`}>
      {items.map((it, i) => (
        <Metric
          key={it.label}
          label={it.label}
          value={it.value}
          accent={it.accent}
          icon={it.icon}
          suffix={it.suffix}
          sub={it.sub}
          delay={it.delay ?? i * 50}
        />
      ))}
    </div>
  );
}

export function DataTable({ columns, rows, empty = 'Not available' }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-ink-muted">{empty}</p>;
  }
  return (
    <div className="table-scroll overflow-hidden rounded-card border border-line">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="bg-card-elevated/70">
            {columns.map((c) => (
              <th
                key={c.key}
                className="whitespace-nowrap border-b border-line px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-ink-muted"
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-b border-line/60 transition-colors duration-200 last:border-b-0 hover:bg-card-elevated/40"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`border-b border-line/60 px-3 py-2.5 align-top text-ink-secondary last:border-b-0 ${
                    c.mono ? 'font-mono text-xs text-ink-muted' : ''
                  }`}
                >
                  {r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Animated progress bar: fills 0% -> value over 800ms (ease-out) on mount.
export function ProgressBar({ value, to = 'bg-gradient-to-r from-cyan to-blue', delay = 0, className = '', h = 3 }) {
  const [w, setW] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setW(Number(value) || 0), 60 + (delay || 0));
    return () => clearTimeout(t);
  }, [value, delay]);

  const pct = Math.max(0, Math.min(100, Number(w) || 0));
  return (
    <div
      className={`overflow-hidden rounded-pill bg-bg-secondary ${className}`}
      style={{ height: `${h * 4}px` }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-pill ${to}`}
        style={{ width: `${pct}%`, transition: 'width 800ms ease-out' }}
      />
    </div>
  );
}

export function StatusDot({ tone = 'ok', pulse = false, size = 'h-2 w-2' }) {
  const colors = {
    ok: 'bg-green',
    warn: 'bg-amber',
    bad: 'bg-red',
    na: 'bg-ink-disabled',
  };
  const pulseClass = pulse ? (tone === 'ok' ? 'pulse-ok' : tone === 'bad' ? 'pulse-bad' : '') : '';
  return <span className={`inline-block shrink-0 rounded-pill ${size} ${colors[tone] || colors.na} ${pulseClass}`} />;
}

export function Skeleton({ className = '' }) {
  return <div className={`skeleton rounded-card ${className}`} />;
}