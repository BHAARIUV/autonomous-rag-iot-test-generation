// Phase 15 — IoT + AI monitoring card system.
// Presentational only: every value arrives via props from REAL backend data.
// When a value is unavailable the card renders "Not available" — nothing is
// ever fabricated (there is no live hardware telemetry in this framework).

import {
  Bot,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  Cpu,
  FlaskConical,
  Gauge,
  Globe,
  Link2,
  PauseCircle,
  Power,
  SearchCheck,
  Server,
  Signal,
  TriangleAlert,
  Wifi,
} from 'lucide-react';
import { isNA } from '../data.js';
import { ProgressBar, StatusDot } from './ui.jsx';

/* Accent chips — cyan/blue/purple only (status colors stay semantic). */
const ACCENT = {
  primary: 'from-cyan to-blue',
  cyan: 'from-cyan to-blue',
  blue: 'from-blue to-purple',
  green: 'from-green to-green',
  purple: 'from-purple to-purple',
};

/* Semantic status chips — green/amber/red reserved for status. */
const SENSOR_STATUS = {
  ok: { label: 'NORMAL', cls: 'border-line-success/60 text-green', dot: 'bg-green' },
  warn: { label: 'WARNING', cls: 'border-line-warn/60 text-amber', dot: 'bg-amber' },
  bad: { label: 'FAULT', cls: 'border-line-error/60 text-red', dot: 'bg-red' },
  na: { label: 'OFFLINE', cls: 'border-line/70 text-ink-disabled', dot: 'bg-ink-disabled' },
};

function AccentIcon({ Icon, accent = 'cyan', size = 17 }) {
  return (
    <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${ACCENT[accent] || ACCENT.cyan} text-white shadow-ai`}>
      <Icon size={size} strokeWidth={2} />
    </span>
  );
}

function StatusPill({ tone = 'na', label, pulse = false }) {
  const st = SENSOR_STATUS[tone] || SENSOR_STATUS.na;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-pill border px-2 py-0.5 text-[11px] font-semibold ${st.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-pill ${st.dot} ${pulse ? (tone === 'ok' ? 'pulse-ok' : tone === 'bad' ? 'pulse-bad' : '') : ''}`} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// SensorCard — single-sensor status tile (temperature, status, counters).
// `value` is a string/number produced by the caller from backend data.
export function SensorCard({
  icon: Icon,
  label,
  value,
  unit,
  tone = 'ok',
  badge,
  accent = 'cyan',
  delay = 0,
  sub,
}) {
  const st = SENSOR_STATUS[tone] || SENSOR_STATUS.na;
  const na = isNA(value);
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/5 to-transparent" />
      <div className="flex items-center gap-2.5">
        <AccentIcon Icon={Icon} accent={accent} />
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
      </div>
      <div className="tab-nums mt-3 flex items-baseline gap-1.5">
        <span className={`text-3xl font-bold leading-none ${na ? 'text-ink-disabled' : 'text-ink'}`}>
          {na ? 'Not available' : value}
        </span>
        {!na && unit && <span className="text-sm font-medium text-ink-muted">{unit}</span>}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold ${st.cls}`}>
          <span className={`h-1.5 w-1.5 rounded-pill ${st.dot}`} />
          {badge || st.label}
        </span>
        {sub ? <span className="truncate text-[11px] text-ink-muted" title={sub}>{sub}</span> : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IotMonitorCard — the "IoT TEST ENVIRONMENT" monitor.
// `supporting` is an optional provenance note (never fabricated telemetry).
export function IotMonitorCard({
  icon: Icon,
  label,
  value,
  unit,
  supporting,
  tone = 'na',
  status,
  accent = 'cyan',
  delay = 0,
}) {
  const st = SENSOR_STATUS[tone] || SENSOR_STATUS.na;
  const shown = status || st.label;
  const na = isNA(value);
  const pulse = tone === 'ok' || tone === 'bad';
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={`pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.03] to-transparent`} />
      <div className="relative flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={Icon} accent={accent} />
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
        </div>
        <StatusPill tone={tone} label={shown} pulse={pulse} />
      </div>
      <div className="tab-nums relative mt-3 flex items-baseline gap-1.5">
        <span className={`text-3xl font-bold leading-none ${na ? 'text-ink-disabled' : 'text-ink'}`}>
          {na ? 'Not available' : value}
        </span>
        {!na && unit && <span className="text-sm font-medium text-ink-muted">{unit}</span>}
      </div>
      {supporting ? (
        <div className="relative mt-2 truncate text-[11px] leading-relaxed text-ink-muted" title={supporting}>
          {supporting}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeviceMonitorCard — device / simulation status.
export function DeviceMonitorCard({ id, label = 'Device under test', state = 'na', firmware, protocol, lastSeen, delay = 0 }) {
  const st = SENSOR_STATUS[state] || SENSOR_STATUS.na;
  const value = isNA(id) ? null : id;
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={Cpu} accent="blue" />
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
        </div>
        <StatusPill tone={state} label={st.label} pulse={state === 'ok' || state === 'bad'} />
      </div>
      <div className="tab-nums mt-3 truncate font-mono text-lg font-bold text-ink" title={value}>
        {value || 'Not available'}
      </div>
      <dl className="mt-3 space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Power size={11} /> Firmware</dt>
          <dd className="font-mono text-ink-secondary">{isNA(firmware) ? 'Not available' : firmware}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Link2 size={11} /> Protocol</dt>
          <dd className="font-mono text-ink-secondary">{isNA(protocol) ? 'Not available' : protocol}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Clock size={11} /> Last seen</dt>
          <dd className="text-ink-secondary">{isNA(lastSeen) ? 'Not available' : lastSeen}</dd>
        </div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MqttMonitorCard — MQTT / communication status (only when data exists).
export function MqttMonitorCard({
  label = 'MQTT',
  topic,
  clientId,
  qualityOfService,
  connected = null,
  lastMessage,
  delay = 0,
}) {
  const tone = connected === true ? 'ok' : connected === false ? 'bad' : 'na';
  const statusLabel = connected === true ? 'ONLINE' : connected === false ? 'OFFLINE' : 'OFFLINE';
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={Wifi} accent="cyan" />
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
        </div>
        <StatusPill tone={tone} label={statusLabel} pulse={tone === 'ok' || tone === 'bad'} />
      </div>
      <div className="tab-nums mt-3 truncate font-mono text-lg font-bold text-ink" title={isNA(topic) ? undefined : topic}>
        {isNA(topic) ? 'Not available' : topic}
      </div>
      <dl className="mt-3 space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Server size={11} /> Client id</dt>
          <dd className="font-mono text-ink-secondary">{isNA(clientId) ? 'Not available' : clientId}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Gauge size={11} /> QOS</dt>
          <dd className="font-mono text-ink-secondary">{isNA(qualityOfService) ? 'Not available' : qualityOfService}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Signal size={11} /> Last message</dt>
          <dd className="truncate text-ink-secondary">{isNA(lastMessage) ? 'Not available' : lastMessage}</dd>
        </div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TestStatusCard — live test-execution summary with coverage progress.
export function TestStatusCard({ passed, failed, errors, skipped, total, coverage, delay = 0, right }) {
  const anyData = Number(total) > 0;
  const partial = Number(failed) > 0 || Number(errors) > 0;
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan/30 to-transparent" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={FlaskConical} accent="blue" />
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Test status</div>
        </div>
        {right || <StatusPill tone={partial ? 'warn' : 'ok'} label={partial ? 'PARTIAL' : 'COMPLETE'} />}
      </div>

      <div className="tab-nums mt-3 flex items-baseline gap-1.5">
        <span className={`text-3xl font-bold leading-none ${anyData ? 'text-ink' : 'text-ink-disabled'}`}>
          {anyData ? passed : 'Not available'}
        </span>
        {anyData && <span className="text-sm font-medium text-ink-muted">passed</span>}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="rounded-pill border border-line-success/50 bg-ok-bg px-2 py-0.5 font-semibold text-green">P {fmt(passed)}</span>
        <span className="rounded-pill border border-line-error/50 bg-err-bg px-2 py-0.5 font-semibold text-red">F {fmt(failed)}</span>
        <span className="rounded-pill border border-line-warn/50 bg-warn-bg px-2 py-0.5 font-semibold text-amber">E {fmt(errors)}</span>
        <span className="rounded-pill border border-line/50 bg-bg-secondary px-2 py-0.5 font-semibold text-ink-muted">S {fmt(skipped)}</span>
      </div>

      <div className="mt-3">
        <div className="mb-1 flex items-center justify-between text-[11px]">
          <span className="font-medium text-ink-muted">Execution coverage</span>
          <span className="tab-nums font-mono font-semibold text-cyan">{isNA(coverage) ? '—' : `${Number(coverage).toFixed(1)}%`}</span>
        </div>
        <ProgressBar value={isNA(coverage) ? 0 : coverage} to="bg-gradient-to-r from-cyan to-blue" delay={100} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CoverageCard — requirement / execution coverage with progress indicator.
export function CoverageCard({ label, value, sub, icon: Icon = Gauge, accent = 'cyan', delay = 0, right }) {
  const na = isNA(value);
  const pct = na ? 0 : Math.max(0, Math.min(100, Number(value)));
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={Icon} accent={accent} />
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
        </div>
        {right}
      </div>
      <div className="tab-nums mt-3 flex items-baseline gap-1.5">
        <span className={`text-3xl font-bold leading-none ${na ? 'text-ink-disabled' : 'text-ink'}`}>
          {na ? 'Not available' : `${pct.toFixed(1)}%`}
        </span>
        {sub && <span className="min-w-0 truncate text-[11px] text-ink-muted" title={sub}>{sub}</span>}
      </div>
      <div className="mt-3">
        <ProgressBar value={pct} to={`bg-gradient-to-r ${ACCENT[accent] || ACCENT.cyan}`} delay={120} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ApiStatusCard — backend / API status (health + connectivity).
export function ApiStatusCard({
  service,
  status = 'na',
  mode,
  apiVersion,
  baseUrl,
  endpoints = [],
  projectName,
  delay = 0,
}) {
  const tone = String(status).toLowerCase();
  const ok = tone === 'ok';
  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AccentIcon Icon={Server} accent="purple" />
          <div className="min-w-0">
            <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Backend / API</div>
            {service ? <div className="truncate text-xs font-medium text-ink-secondary">{service}</div> : null}
          </div>
        </div>
        <StatusPill tone={ok ? 'ok' : 'bad'} label={ok ? 'ONLINE' : 'OFFLINE'} pulse={ok} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="inline-flex items-center gap-1.5 rounded-pill border border-line-success/50 bg-ok-bg px-2 py-0.5 font-semibold text-green">
          <StatusDot tone="ok" pulse={ok} size="h-1.5 w-1.5" />
          {ok ? 'Healthy' : 'Unreachable'}
        </span>
        <span className="rounded-pill border border-line/60 bg-bg-secondary px-2 py-0.5 font-semibold text-ink-secondary">api v{apiVersion}</span>
        <span className="rounded-pill border border-line/60 bg-bg-secondary px-2 py-0.5 font-semibold text-cyan">mode: {mode}</span>
      </div>

      <div className="mt-3 space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Globe size={11} /> Base URL</dt>
          <dd className="truncate font-mono text-ink-secondary">{isNA(baseUrl) ? 'Not available' : baseUrl}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1.5 text-ink-muted"><Bot size={11} /> Project</dt>
          <dd className="truncate text-ink-secondary">{isNA(projectName) ? 'Not available' : projectName}</dd>
        </div>
      </div>

      {endpoints.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Endpoints</div>
          <div className="flex flex-wrap gap-1.5">
            {endpoints.slice(0, 6).map((ep) => (
              <code key={ep} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-blue">
                {ep}
              </code>
            ))}
            {endpoints.length > 6 && (
              <span className="px-1 py-0.5 text-[10px] text-ink-disabled">+{endpoints.length - 6}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fault alert banner — health / warning / actual-fault states.
const ALERT_STYLE = {
  ok: {
    ring: 'border-line-success/60',
    chip: 'bg-ok-bg text-green border-line-success/60',
    dot: 'bg-green',
    grad: 'from-green/12 via-transparent to-transparent',
    Icon: CircleCheck,
  },
  warn: {
    ring: 'border-line-warn/60',
    chip: 'bg-warn-bg text-amber border-line-warn/60',
    dot: 'bg-amber',
    grad: 'from-amber/12 via-transparent to-transparent',
    Icon: CircleAlert,
  },
  bad: {
    ring: 'border-line-error/60',
    chip: 'bg-err-bg text-red border-line-error/60',
    dot: 'bg-red',
    grad: 'from-red/12 via-transparent to-transparent',
    Icon: TriangleAlert,
  },
  na: {
    ring: 'border-line/60',
    chip: 'bg-bg-secondary text-ink-muted border-line/70',
    dot: 'bg-ink-disabled',
    grad: 'from-ink-disabled/10 via-transparent to-transparent',
    Icon: CircleDashed,
  },
};

export function AlertBanner({ tone = 'na', title, lede, right }) {
  const s = ALERT_STYLE[tone] || ALERT_STYLE.na;
  const Icon = s.Icon;
  return (
    <div
      className={`anim-entry relative flex flex-wrap items-center gap-3 overflow-hidden rounded-card border bg-card px-4 py-3.5 shadow-card ${s.ring}`}
      style={{ animationDelay: '0ms' }}
    >
      <div className={`pointer-events-none absolute inset-y-0 left-0 w-1 bg-gradient-to-b ${s.dot}`} />
      <div className={`pointer-events-none absolute inset-0 bg-gradient-to-r ${s.grad}`} />
      <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border ${s.chip}`}>
        <Icon size={18} strokeWidth={2} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-ink">{title}</div>
        {lede ? <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{lede}</p> : null}
      </div>
      {right}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fault card — actual injected fault + real detection evidence.
const FAULT_STYLES = {
  ok: {
    tile: 'border-line-success/70',
    chip: 'bg-ok-bg text-green border-line-success/70',
    dot: 'bg-green',
    top: 'bg-gradient-to-r from-green/70 to-green/20',
  },
  warn: {
    tile: 'border-line-warn/70',
    chip: 'bg-warn-bg text-amber border-line-warn/70',
    dot: 'bg-amber',
    top: 'bg-gradient-to-r from-amber/70 to-amber/20',
  },
  bad: {
    tile: 'border-line-error/70',
    chip: 'bg-err-bg text-red border-line-error/70',
    dot: 'bg-red',
    top: 'bg-gradient-to-r from-red/70 to-red/20',
  },
  na: {
    tile: 'border-line-warn/60',
    chip: 'bg-bg-secondary text-ink-muted border-line/70',
    dot: 'bg-ink-disabled',
    top: 'bg-gradient-to-r from-ink-disabled/60 to-ink-disabled/20',
  },
};

const STATUS_ICON = {
  DETECTED: SearchCheck,
  MISSED: TriangleAlert,
  NOT_EXECUTED: PauseCircle,
};

export function FaultCard({ fault, delay = 0 }) {
  const status = String(fault.detection_status || '').toUpperCase();
  const st =
    status === 'DETECTED' ? FAULT_STYLES.ok : status === 'MISSED' ? FAULT_STYLES.bad : FAULT_STYLES.na;
  const Icon = STATUS_ICON[status] || PauseCircle;
  const label = isNA(fault.detection_status) ? 'NOT EXECUTED' : String(fault.detection_status);
  const observed = isNA(fault.execution_result) ? null : String(fault.execution_result);

  return (
    <div
      className="card-hover anim-entry relative overflow-hidden rounded-card border bg-card p-4 shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={`pointer-events-none absolute inset-x-0 top-0 h-1 ${st.top}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border ${st.chip}`}>
            <Icon size={17} strokeWidth={2} />
          </span>
          <div>
            <div className="font-mono text-[13px] font-bold text-ink">{fault.fault_id}</div>
            <div className="text-[11px] uppercase tracking-wider text-ink-muted">{fault.fault_type}</div>
          </div>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold ${st.chip}`}>
          <span className={`h-1.5 w-1.5 rounded-pill ${st.dot}`} />
          {label}
        </span>
      </div>

      {fault.requirement_ids && fault.requirement_ids.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-ink-muted">Requirement:</span>
          {fault.requirement_ids.map((id) => (
            <code key={id} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[11px] text-cyan">
              {id}
            </code>
          ))}
        </div>
      )}

      <p className="mt-3 text-xs leading-relaxed text-ink-secondary">
        {isNA(fault.detection_evidence) ? 'No execution evidence recorded for this fault.' : fault.detection_evidence}
      </p>

      {fault.related_test_case_ids && fault.related_test_case_ids.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-ink-muted">Test case:</span>
          {fault.related_test_case_ids.map((id) => (
            <code key={id} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[11px] text-blue">
              {id}
            </code>
          ))}
        </div>
      )}

      {observed && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-card border border-line/70 bg-bg-secondary/60 px-2.5 py-1.5">
            <div className="text-[10px] uppercase tracking-wider text-ink-muted">Expected</div>
            <div className="text-xs font-semibold text-ink-secondary">Assertion FAIL on injection</div>
          </div>
          <div className="rounded-card border border-line/70 bg-bg-secondary/60 px-2.5 py-1.5">
            <div className="text-[10px] uppercase tracking-wider text-ink-muted">Observed</div>
            <div className={`text-xs font-semibold ${observed.toUpperCase() === 'FAIL' ? 'text-red' : 'text-green'}`}>
              {observed}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const MISSED_STYLE = {
  DETECTED: 'text-green',
  MISSED: 'text-red',
  NOT_EXECUTED: 'text-ink-disabled',
  DEFAULT: 'text-ink-muted',
};

export function FaultStatus({ fault }) {
  const status = String(fault.detection_status || '').toUpperCase();
  const cls = MISSED_STYLE[status] || MISSED_STYLE.DEFAULT;
  const Icon = STATUS_ICON[status] || CircleDashed;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${cls}`}>
      <Icon size={13} strokeWidth={2} />
      {isNA(fault.detection_status) ? 'NOT EXECUTED' : String(fault.detection_status)}
    </span>
  );
}

/* Local helper — formatted number with "Not available" → "—". */
function fmt(value) {
  if (isNA(value)) return '—';
  return String(value);
}

export { CircleX }; // back-compat re-export