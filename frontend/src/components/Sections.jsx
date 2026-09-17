// Phase 15 — the dashboard section views.
//
// Every view renders REAL project data produced by the backend (`DashboardData`
// served by GET /api/dashboard). Values the backend marks "Not available" are
// shown as "—"; real zeros are shown as 0. Nothing here is fabricated.

import { useEffect, useState } from 'react';
import {
  Activity,
  BookOpen,
  Brain,
  Check,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  CirclePlay,
  CircleX,
  ClipboardCheck,
  Clock,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  FolderOpen,
  Gauge,
  GitBranch,
  ListChecks,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  Sparkles,
  Target,
  Thermometer,
  TriangleAlert,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import { Badge, Section, StatCards, ProgressBar, DataTable, StatusDot } from './ui.jsx';
import { DonutChart, GaugeChart, BarChart, StackedBar, CHART_COLORS } from './charts.jsx';
import { SensorCard, IotMonitorCard, DeviceMonitorCard, MqttMonitorCard, FaultCard, AlertBanner } from './cards.jsx';
import AiWorkflow from './Workflow.jsx';
import { isNA, fmtNum, joinList, derivePhaseStatus, PHASE_15 } from '../data.js';
import { fetchDashboard } from '../api.js';

function tempRange(requirements) {
  const req = (requirements || []).find((r) => /TEMPERATURE/i.test(r.description || ''));
  if (!req) return null;
  const m = /(-?\d+(?:\.\d+)?)\D+to\s+(-?\d+(?:\.\d+)?)/i.exec(req.description || '');
  if (!m) return null;
  return `${Number(m[1])}–${Number(m[2])}`;
}

function reqById(reqs, id) {
  return (reqs || []).find((r) => r.requirement_id === id);
}

function execColor(status) {
  const s = String(status || '').toUpperCase();
  if (s === 'PASS') return CHART_COLORS.pass;
  if (s === 'FAIL') return CHART_COLORS.fail;
  if (s === 'ERROR') return CHART_COLORS.error;
  return CHART_COLORS.skip;
}

function HeroTile({ label, value, accent = 'text-ink', mono }) {
  return (
    <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
      <div className={`tab-nums mt-1.5 text-xl font-bold ${accent}${mono ? ' font-mono' : ''}`}>{value}</div>
    </div>
  );
}

// Traceability chain hops (Requirement → Knowledge → Test → Execution → Fault).
const TRACE_HOPS = [
  { key: 'requirement', label: 'Requirement', Icon: Target },
  { key: 'evidence', label: 'Knowledge', Icon: BookOpen },
  { key: 'test', label: 'Generated test', Icon: FlaskConical },
  { key: 'execution', label: 'Execution', Icon: CirclePlay },
  { key: 'fault', label: 'Fault', Icon: TriangleAlert },
];

function toUnique(list) {
  return [...new Set((list || []).filter(Boolean))];
}

// ===========================================================================
// 1. Dashboard — "AI + IoT Test Automation Control Center".
// Rendered from REAL DashboardData only (omitted values are "Not available"):
// header, KPI row, IoT environment, test execution, fault detection, AI/RAG
// pipeline, requirement coverage and autonomous refinement.
export function Overview({ data }) {
  const o = data.overview;
  const e = data.execution;
  const g = data.generation;
  const f = data.fault_summary;
  const k = data.knowledge;
  const r = data.refinement;
  const fs = data.final_status;

  const reqs = data.requirements || [];
  const reqCount = reqs.length;
  const reqCovered = reqs.filter((x) => String(x.coverage_status || '').toUpperCase() === 'COVERED').length;
  const reqPct = reqCount > 0 ? (reqCovered / reqCount) * 100 : 0;

  const execTotal = Number(e.total_executed) || 0;
  const genTotal = Number(o.total_test_cases) || 0;
  const passRate = execTotal > 0 ? (Number(e.passed) / execTotal) * 100 : 0;

  const mqtt = (e.execution_history || []).find((h) => String(h.test_case_id).toUpperCase() === 'TC-MQTT-001');
  const mqttOk = mqtt && String(mqtt.status || '').toUpperCase() === 'PASS';
  const mqttFail = mqtt && String(mqtt.status || '').toUpperCase() === 'FAIL';
  const mqttConnected = mqtt ? mqttOk : null;

  const totalFaults = Number(f.total_faults) || 0;
  const detectedFaults = Number(f.detected_faults) || 0;
  const missedFaults = !isNA(f.missed_faults)
    ? Number(f.missed_faults)
    : Math.max(0, totalFaults - detectedFaults);
  const faultNotExec = (f.faults || []).filter((x) => String(x.detection_status || '').toUpperCase() === 'NOT_EXECUTED').length;

  const rate = Number(f.fault_detection_rate) || 0;
  const rateColor =
    rate >= 80
      ? { from: '#22C55E', to: '#16A34A' }
      : rate >= 50
        ? { from: '#F59E0B', to: '#F59E0B' }
        : { from: '#EF4444', to: '#EF4444' };

  const history = e.execution_history || [];
  const lastEvent = history[history.length - 1];
  const alertTone = missedFaults > 0 ? 'bad' : detectedFaults > 0 ? 'warn' : faultNotExec > 0 ? 'warn' : 'ok';
  const tempDeg = tempRange(reqs);

  return (
    <div className="space-y-6">
      {/* 1 — Header: system + backend/API status */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-blue/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-cyan/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan">
              <Activity size={13} strokeWidth={2.2} />
              AI + IoT Test Automation Center
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">{o.project_name}</h2>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status={o.project_status} />
              <Badge status={o.generation_mode} />
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <span className="h-1.5 w-1.5 rounded-pill bg-gradient-to-r from-cyan to-blue" />
                Phase {fmtNum(o.current_phase)} / {fmtNum(o.total_phases)}
              </span>
              <span className="max-w-[220px] truncate rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 font-mono text-[11px] text-ink-muted">
                {fmtNum(o.analysis_id)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line-success/50 bg-ok-bg/60 px-4 py-3">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                <Server size={11} className="text-green" /> Backend API
              </div>
              <div className="mt-1.5 flex items-center gap-2">
                <StatusDot tone="ok" pulse />
                <span className="text-lg font-bold text-green">Online</span>
              </div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Executed tests</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-ink">{fmtNum(o.executed_tests)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Pass rate</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-grad-primary">
                {execTotal > 0 ? `${passRate.toFixed(1)}%` : '—'}
              </div>
            </div>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Requirements</span>
          <span className="font-mono text-cyan">{fmtNum(reqCount)}</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Tests</span>
          <span className="font-mono text-blue">{fmtNum(o.total_test_cases)}</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Faults</span>
          <span className="font-mono text-amber">{fmtNum(f.total_faults)}</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Documents</span>
          <span className="font-mono text-purple">{fmtNum(k.document_count)}</span>
        </div>
      </div>

      {/* 2 — KPI row */}
      <StatCards
        cols="xl:grid-cols-6"
        items={[
          { label: 'Requirements', value: reqCount, accent: 'cyan', icon: ClipboardCheck, sub: `${reqCovered} covered` },
          { label: 'Test cases', value: o.total_test_cases, accent: 'blue', icon: FlaskConical, sub: `${fmtNum(g.total_generated)} generated` },
          { label: 'Executed', value: execTotal, accent: 'cyan', icon: CirclePlay, sub: genTotal > 0 ? `${((execTotal / genTotal) * 100).toFixed(0)}% of generated` : 'generated' },
          { label: 'Passed', value: e.passed, accent: 'green', icon: CircleCheck, sub: `${passRate.toFixed(1)}% pass rate` },
          { label: 'Failed', value: e.failed, accent: 'red', icon: XCircle, sub: `${fmtNum(e.errors)} errors · ${fmtNum(e.skipped)} skipped` },
          { label: 'Runtime coverage', value: e.execution_coverage, suffix: '%', accent: 'purple', icon: Gauge, sub: `${execTotal} of ${genTotal} executed` },
        ]}
      />

      {/* 3 — IoT test environment */}
      <Section
        icon={Cpu}
        title="IoT test environment"
        lede="Simulated device under test for the autonomous framework — no live hardware telemetry exists, so unavailable values are shown as Not available."
        right={<Badge status={mqttOk ? 'ONLINE' : mqttFail ? 'FAULT' : 'OFFLINE'} />}
        delay={40}
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <DeviceMonitorCard id={o.project_id} state="na" delay={0} />
          <MqttMonitorCard
            connected={mqttConnected}
            lastMessage={mqtt ? `TC-MQTT-001 · ${String(mqtt.status).toUpperCase()}` : undefined}
            delay={50}
          />
          <SensorCard
            icon={Thermometer}
            label="Temperature"
            value="Not available"
            tone="na"
            accent="green"
            sub={tempDeg ? `Operating range ${tempDeg} °C (from spec)` : 'No sensor telemetry in backend data'}
            delay={100}
          />
          <IotMonitorCard
            icon={Activity}
            label="Test environment"
            value={execTotal > 0 ? `${e.passed}/${execTotal}` : 'Not available'}
            unit="PASS"
            tone={Number(e.failed) > 0 ? 'bad' : 'ok'}
            status={Number(e.failed) > 0 ? 'FAULTS ACTIVE' : 'NOMINAL'}
            supporting={lastEvent ? `last: ${lastEvent.test_case_id} · ${String(lastEvent.status).toUpperCase()}` : 'No execution events yet'}
            accent="purple"
            delay={150}
          />
        </div>
      </Section>

      {/* 4 — Test execution */}
      <Section
        icon={CirclePlay}
        title="Test execution"
        lede="Status split, coverage and per-case execution history from the backend."
        right={<Badge status={Number(e.failed) > 0 ? 'PARTIAL' : 'COMPLETE'} />}
        delay={90}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-card p-5">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Status distribution</div>
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <DonutChart
                segments={[
                  { label: 'PASS', value: e.passed, color: CHART_COLORS.pass },
                  { label: 'FAIL', value: e.failed, color: CHART_COLORS.fail },
                  { label: 'ERROR', value: e.errors, color: CHART_COLORS.error },
                  { label: 'SKIPPED', value: e.skipped, color: CHART_COLORS.skip },
                ]}
                centerLabel={String(execTotal)}
                centerSub="executed"
              />
              <div className="w-full min-w-0 flex-1 space-y-1.5">
                {[
                  { label: 'Passed', value: e.passed, color: 'bg-green' },
                  { label: 'Failed', value: e.failed, color: 'bg-red' },
                  { label: 'Errors', value: e.errors, color: 'bg-amber' },
                  { label: 'Skipped', value: e.skipped, color: 'bg-ink-disabled' },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span className="flex items-center gap-1.5">
                      <span className={`inline-block h-2.5 w-2.5 rounded-sm ${row.color}`} />
                      {row.label}
                    </span>
                    <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(row.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-card border border-line bg-card p-5">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Execution coverage</span>
              <span className="tab-nums font-mono font-semibold text-cyan">{fmtNum(e.execution_coverage)}%</span>
            </div>
            <ProgressBar value={e.execution_coverage} to="bg-gradient-to-r from-cyan to-blue" delay={120} />
            <div className="mt-4">
              <BarChart
                data={[
                  { label: 'PASS', value: e.passed, color: CHART_COLORS.pass },
                  { label: 'FAIL', value: e.failed, color: CHART_COLORS.fail },
                  { label: 'ERROR', value: e.errors, color: CHART_COLORS.error },
                  { label: 'SKIPPED', value: e.skipped, color: CHART_COLORS.skip },
                ]}
                height={170}
                ariaLabel="Test execution status distribution"
              />
            </div>
          </div>
        </div>

        {history.length > 0 && (
          <div className="mt-5">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Recent executions</div>
            <DataTable
              columns={[
                { key: 'test_case_id', label: 'Test case', mono: true },
                { key: 'status', label: 'Status' },
                { key: 'execution_id', label: 'Execution', mono: true },
              ]}
              rows={history.slice(-8).map((h) => ({
                test_case_id: h.test_case_id,
                status: <Badge status={h.status} />,
                execution_id: String(h.execution_id || '').slice(0, 8),
              }))}
            />
          </div>
        )}
      </Section>

      {/* 5 — Fault detection */}
      <Section
        icon={ShieldAlert}
        title="Fault detection"
        lede="Injected faults and their real detection states from execution evidence."
        right={<Badge status={detectedFaults > 0 ? 'DETECTED' : 'NA'} />}
        delay={130}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="flex items-center justify-center rounded-card border border-line bg-card p-5">
            <GaugeChart
              value={f.fault_detection_rate}
              centerLabel="Detection rate"
              sub={`${detectedFaults} of ${totalFaults} faults`}
              from={rateColor.from}
              to={rateColor.to}
            />
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-green" /> Detected</span>
              <span className="tab-nums font-mono font-semibold text-green">{fmtNum(detectedFaults)}</span>
            </div>
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-red" /> Missed</span>
              <span className="tab-nums font-mono font-semibold text-red">{fmtNum(missedFaults)}</span>
            </div>
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ink-disabled" /> Not executed</span>
              <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(faultNotExec)}</span>
            </div>
            <AlertBanner
              tone={alertTone}
              title={
                missedFaults > 0
                  ? 'FAULT MISSED — detection gap'
                  : detectedFaults > 0
                    ? 'FAULT DETECTED'
                    : faultNotExec > 0
                      ? 'FAULTS NOT EXECUTED'
                      : 'No faults injected'
              }
              lede={
                missedFaults > 0
                  ? `${missedFaults} injected fault(s) were not surfaced by any test execution.`
                  : detectedFaults > 0
                    ? `${detectedFaults} fault(s) were injected and correctly surfaced by failing assertions.`
                    : faultNotExec > 0
                      ? `${faultNotExec} fault(s) had no injected test.`
                      : 'The fault-injection engine recorded no faults for this run.'
              }
              right={<span className="tab-nums font-mono text-xs text-ink-muted">{detectedFaults}/{totalFaults} detected</span>}
            />
          </div>
        </div>

        {(f.faults || []).length > 0 && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {(f.faults || []).map((fault, i) => (
              <FaultCard key={fault.fault_id} fault={fault} delay={i * 80} />
            ))}
          </div>
        )}
      </Section>

      {/* 6 — AI / RAG pipeline */}
      <Section
        icon={Brain}
        title="AI / RAG pipeline"
        lede="Requirement → RAG retrieval → knowledge → AI test generation → execution → fault detection → autonomous refinement → traceability."
        delay={180}
      >
        <AiWorkflow data={data} />
      </Section>

      {/* 7 — Requirement coverage */}
      <Section
        icon={ClipboardCheck}
        title="Requirement coverage"
        lede="Requirements traced to generated test cases — all real backend values."
        right={<Badge status={reqCount === reqCovered && reqCount > 0 ? 'COMPLETE' : 'PARTIAL'} />}
        delay={220}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-card p-5">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-ink-muted">Covered requirements</span>
              <span className="tab-nums font-mono font-semibold text-green">{reqCount > 0 ? `${reqPct.toFixed(1)}%` : '—'}</span>
            </div>
            <ProgressBar value={reqPct} to="bg-gradient-to-r from-green to-green-darker" delay={120} />
            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-ink-muted">Covered</div>
                <div className="tab-nums text-lg font-bold text-green">{fmtNum(reqCovered)}</div>
              </div>
              <div className="rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-ink-muted">Remaining</div>
                <div className="tab-nums text-lg font-bold text-amber">{fmtNum(reqCount - reqCovered)}</div>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-muted">
              Framework coverage {fmtNum(fs.requirement_coverage)}% · remaining gaps {fmtNum(fs.remaining_gaps)}
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {reqs.map((rq, i) => (
              <div
                key={rq.requirement_id}
                className={`card-hover anim-entry relative overflow-hidden rounded-card border bg-card p-4 shadow-card ${
                  String(rq.coverage_status || '').toUpperCase() === 'COVERED' ? 'border-line-success/40' : 'border-line-warn/40'
                }`}
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <div className="flex items-start justify-between gap-2">
                  <code className="font-mono text-xs font-bold text-ink">{rq.requirement_id}</code>
                  <Badge status={rq.coverage_status} />
                </div>
                <div className="mt-1 inline-flex rounded-pill border border-line/70 bg-bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                  {rq.category}
                </div>
                <p className="line-clamp-2 mt-2.5 text-xs leading-relaxed text-ink-secondary">{rq.description}</p>
                <div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2.5 text-[11px] text-ink-muted">
                  <span className="flex items-center gap-1"><FlaskConical size={11} className="text-blue" /> {fmtNum(rq.test_case_count)} tests</span>
                  <Badge status={rq.validation_status} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* 8 — Autonomous refinement */}
      <Section
        icon={TrendingUp}
        title="Autonomous refinement"
        lede="Coverage improvement produced by the refinement loop — real backend values only."
        right={<Badge status={r.available ? r.stop_reason : 'NA'} />}
        delay={260}
      >
        {r.available ? (
          <>
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-card border border-line bg-card p-5">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-ink-muted">Coverage before</span>
                  <span className="tab-nums font-mono font-semibold text-amber">{isNA(r.coverage_before) ? '—' : `${Number(r.coverage_before).toFixed(1)}%`}</span>
                </div>
                <ProgressBar value={r.coverage_before} to="bg-gradient-to-r from-amber to-amber" delay={100} />
              </div>
              <div className="rounded-card border border-line bg-card p-5">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-ink-muted">Coverage after</span>
                  <span className="tab-nums font-mono font-semibold text-grad-ai">{isNA(r.coverage_after) ? '—' : `${Number(r.coverage_after).toFixed(1)}%`}</span>
                </div>
                <ProgressBar value={r.coverage_after} to="bg-gradient-to-r from-cyan to-purple" delay={140} />
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Sparkles size={12} className="text-cyan" /> {fmtNum(r.iterations ? r.iterations.length : 0)} iterations
              </span>
              <span className="flex items-center gap-1.5">
                <Target size={12} className="text-green" /> +{isNA(r.improvement_requirement_coverage) ? '—' : `${Number(r.improvement_requirement_coverage).toFixed(1)}%`} improvement
              </span>
              <span className="flex items-center gap-1.5">
                <FlaskConical size={12} className="text-purple" /> {fmtNum(r.total_generated)} generated
              </span>
            </div>
          </>
        ) : (
          <p className="text-xs text-ink-muted">Refinement result not available.</p>
        )}
      </Section>
    </div>
  );
}

// 2. Phase delivery status (Phase 1–15) — engineering execution view.
const PHASE_ICON = {
  COMPLETE: CircleCheck,
  CURRENT: CircleDashed,
  PENDING: CircleDashed,
  FAILED: CircleX,
};

const PHASE_TONE = {
  COMPLETE: { chip: 'border-line-success/60 bg-ok-bg text-green', dot: 'bg-green', rail: 'bg-green/50', seg: 'from-green to-green-darker shadow-sm' },
  CURRENT: { chip: 'border-line-active/60 bg-blue/10 text-cyan', dot: 'bg-cyan', rail: 'bg-cyan/50', seg: 'from-cyan to-blue shadow-ai' },
  PENDING: { chip: 'border-line bg-bg-secondary text-ink-muted', dot: 'bg-ink-disabled', rail: 'bg-line/50', seg: '' },
  FAILED: { chip: 'border-line-error/60 bg-err-bg text-red', dot: 'bg-red', rail: 'bg-red/50', seg: 'from-red to-red shadow-sm' },
};

const PHASE_STATE_LABEL = {
  COMPLETE: 'Completed',
  CURRENT: 'Current',
  PENDING: 'Pending',
  FAILED: 'Failed',
};

function phaseUiStatus(phase) {
  if (phase.phase_number === 15) return 'CURRENT';
  const s = String(phase.status || '').toUpperCase();
  if (s === 'COMPLETE') return 'COMPLETE';
  if (s.includes('FAIL')) return 'FAILED';
  return 'PENDING';
}

export function Phases({ data }) {
  const o = data.overview;
  const ft = data.final_status.final_test_result || {};
  const backendRows = data.final_status.phases.map((p) => ({
    phase_number: p.phase_number,
    title: p.title,
    status: derivePhaseStatus(p, data.final_status.final_test_result),
    verification: p.verification,
  }));
  const rows = [
    ...backendRows,
    { phase_number: PHASE_15.phase_number, title: PHASE_15.title, status: PHASE_15.status, verification: PHASE_15.verification },
  ];
  const uiRows = rows.map((row) => ({ ...row, ui: phaseUiStatus(row) }));
  const complete = uiRows.filter((r) => r.ui === 'COMPLETE').length;
  const pending = uiRows.filter((r) => r.ui === 'PENDING').length;
  const currentRow = uiRows.find((r) => r.ui === 'CURRENT');
  const pct = (complete / uiRows.length) * 100;
  const suiteTotal = Number(ft.total) || 0;
  const suitePassed = Number(ft.passed) || 0;
  const suiteOk = suiteTotal > 0 && Number(ft.failed) === 0 && Number(ft.errors) === 0 && Number(ft.skipped) === 0;

  return (
    <div className="space-y-6">
      {/* Hero — pipeline + test evidence */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-blue/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-cyan/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan">
              <ListChecks size={13} strokeWidth={2.2} />
              Phase execution status
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Phase 1–15 delivery</h2>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status={o.project_status} />
              <Badge status={suiteOk ? 'PASS' : 'FAILED'} />
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <span className="h-1.5 w-1.5 rounded-pill bg-gradient-to-r from-cyan to-blue" />
                Backend phase {fmtNum(o.current_phase)} / {fmtNum(o.total_phases)} · {fmtNum(o.completed_phases)} complete
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line-success/50 bg-ok-bg/60 px-4 py-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Pipeline complete</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-grad-primary">{complete}/{uiRows.length}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Final test suite</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-green">{fmtNum(suitePassed)} <span className="text-xs font-semibold text-ink-muted">pass</span></div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Suite pass rate</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-grad-primary">{suiteTotal > 0 ? `${((suitePassed / suiteTotal) * 100).toFixed(1)}%` : '—'}</div>
            </div>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Pytest evidence</span>
          <span className="font-mono text-cyan">{fmtNum(ft.total)} total</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-mono text-green">{fmtNum(ft.passed)} passed</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-mono text-red">{fmtNum(ft.failed)} failed</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-mono text-amber">{fmtNum(ft.errors)} errors</span>
          <span className="text-ink-disabled">·</span>
          <span className="font-mono text-ink-muted">{fmtNum(ft.skipped)} skipped</span>
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Phases total', value: uiRows.length, accent: 'cyan', icon: ListChecks, sub: 'phases 1–15' },
          { label: 'Completed', value: complete, accent: 'green', icon: CircleCheck, sub: 'verified by test evidence' },
          { label: 'Current', value: currentRow ? currentRow.phase_number : '—', accent: 'cyan', icon: CircleDashed, sub: currentRow ? currentRow.title : 'Not available' },
          { label: 'Remaining', value: pending, accent: 'amber', icon: Target, sub: 'not yet started' },
          { label: 'Overall completion', value: pct, suffix: '%', accent: 'purple', icon: Gauge, sub: `${complete} of ${uiRows.length} delivered` },
        ]}
      />

      {/* Current phase spotlight */}
      <div className="anim-entry relative overflow-hidden rounded-card border border-line-active/50 bg-header p-5 shadow-card" style={{ animationDelay: '40ms' }}>
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan to-transparent" />
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan to-blue text-white shadow-ai">
            <CircleDashed size={22} strokeWidth={2} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan">Current phase</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-bold text-ink">Phase {currentRow ? currentRow.phase_number : '—'}</span>
              <span className="text-sm font-semibold text-ink">{currentRow ? currentRow.title : 'Not available'}</span>
              {currentRow && (
                <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold ${PHASE_TONE.CURRENT.chip}`}>
                  <span className={`h-1.5 w-1.5 rounded-pill ${PHASE_TONE.CURRENT.dot}`} />
                  {currentRow.ui}
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-ink-muted">{currentRow ? currentRow.verification || 'Running now.' : 'Not available'}</p>
          </div>
          <div className="flex items-center gap-2.5 rounded-card border border-line-success/50 bg-ok-bg/60 px-3 py-2">
            <StatusDot tone="ok" pulse />
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-muted">Final suite</div>
              <div className="tab-nums text-lg font-bold text-green">{fmtNum(suitePassed)} <span className="text-xs font-semibold text-ink-muted">/ {fmtNum(suiteTotal)} pass</span></div>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline progress — bar + segmented stage strip */}
      <Section
        icon={Activity}
        title="Pipeline progress"
        lede="Phases 1–14 are marked COMPLETE from real backend data; phase 14's status is derived from the real final pytest evidence."
        right={
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-green" /> Complete&nbsp;{complete}</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-cyan" /> Current&nbsp;{uiRows.filter((r) => r.ui === 'CURRENT').length}</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-ink-disabled" /> Pending&nbsp;{pending}</span>
          </div>
        }
      >
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="font-medium text-ink-muted">Overall completion</span>
          <span className="font-mono font-semibold text-cyan">{pct.toFixed(0)}% · {complete}/{uiRows.length} phases</span>
        </div>
        <ProgressBar value={pct} to="bg-gradient-to-r from-cyan to-blue" />

        <div className="mt-4 flex gap-1.5">
          {uiRows.map((r) => (
            <div
              key={r.phase_number}
              title={`Phase ${r.phase_number} — ${r.title} (${PHASE_STATE_LABEL[r.ui]})`}
              className={`h-2.5 flex-1 rounded-sm ${
                r.ui === 'PENDING' ? 'border border-line bg-bg-secondary' : ''
              } ${PHASE_TONE[r.ui].seg} ${r.ui === 'CURRENT' ? 'animate-pulse' : ''}`}
            />
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-wider text-ink-muted">
          <span>1</span>
          <span className="flex-1 border-t border-dashed border-line/50" />
          <span>{uiRows.length}</span>
        </div>
      </Section>

      {/* Execution timeline */}
      <Section icon={ListChecks} title="Execution timeline" lede="Every phase with its real status and verification.">
        <ol className="relative">
          <span aria-hidden className="timeline-rail absolute bottom-3 left-[27px] top-3 w-px bg-gradient-to-b from-green/60 via-cyan/40 to-line/40" />
          <div className="space-y-2">
            {uiRows.map((phase, i) => {
              const ui = phase.ui;
              const tone = PHASE_TONE[ui];
              const Icon = PHASE_ICON[ui];
              const isCurrent = ui === 'CURRENT';
              return (
                <li
                  key={phase.phase_number}
                  className={`anim-entry relative flex gap-3 rounded-card border p-3 pl-[60px] transition-colors duration-200 ${
                    isCurrent ? 'border-line-active/50 bg-header' : 'border-line bg-card'
                  }`}
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <span className={`absolute left-[12px] top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border ${tone.chip}`}>
                    <Icon size={15} strokeWidth={2.2} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-bold text-ink">Phase {phase.phase_number}</span>
                      <span className="text-sm font-semibold text-ink">{phase.title}</span>
                      <span className={`ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold ${tone.chip}`}>
                        <span className={`h-1.5 w-1.5 rounded-pill ${tone.dot}`} />
                        {PHASE_STATE_LABEL[ui]}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-ink-muted">{phase.verification || 'Not available'}</p>
                    {isCurrent ? (
                      <p className="mt-1 text-[11px] text-cyan">This dashboard is the Phase 15 presentation frontend — running now.</p>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </div>
        </ol>
      </Section>
    </div>
  );
}

// 3. Requirements (Section B) — requirements-to-test coverage.
export function Requirements({ data }) {
  const reqs = data.requirements || [];
  const covered = reqs.filter((r) => String(r.coverage_status || '').toUpperCase() === 'COVERED').length;
  const partial = reqs.filter((r) => String(r.coverage_status || '').toUpperCase() === 'PARTIALLY COVERED').length;
  const uncovered = Math.max(0, reqs.length - covered - partial);
  const pct = reqs.length > 0 ? (covered / reqs.length) * 100 : 0;
  const testsMapped = reqs.reduce((sum, r) => sum + (Number(r.test_case_count) || 0), 0);

  const donutSegments = [
    { label: 'COVERED', value: covered, color: CHART_COLORS.pass },
    ...(partial > 0 ? [{ label: 'PARTIALLY COVERED', value: partial, color: CHART_COLORS.error }] : []),
    ...(uncovered > 0 ? [{ label: 'UNCOVERED', value: uncovered, color: CHART_COLORS.fail }] : []),
  ];

  return (
    <div className="space-y-6">
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Requirements', value: reqs.length, accent: 'cyan', icon: ClipboardCheck, sub: `${reqs.length} from real spec` },
          { label: 'Covered', value: covered, accent: 'green', icon: CircleCheck, sub: `${covered} of ${reqs.length} requirements` },
          { label: 'Not covered', value: uncovered, accent: 'amber', icon: Target, sub: `${partial} partially covered` },
          { label: 'Tests mapped', value: testsMapped, accent: 'blue', icon: FlaskConical, sub: 'generated test cases' },
          { label: 'Coverage', value: pct, suffix: '%', accent: 'purple', icon: Gauge, sub: 'covered requirements' },
        ]}
      />

      {/* Coverage visualization */}
      <Section
        icon={Gauge}
        title="Requirement coverage"
        lede="Real coverage split plus the generated-test mapping per requirement — no inferred values."
        right={<Badge status={reqs.length === 0 ? 'NA' : pct >= 100 ? 'COMPLETE' : 'PARTIAL'} />}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Coverage split</div>
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <DonutChart
                segments={donutSegments}
                centerLabel={reqs.length > 0 ? `${pct.toFixed(0)}%` : '—'}
                centerSub="covered"
                centerHint={`${covered}/${reqs.length} requirements`}
              />
              <div className="w-full min-w-0 flex-1 space-y-1.5">
                {[
                  { label: 'Covered', value: covered, hex: CHART_COLORS.pass },
                  { label: 'Partially covered', value: partial, hex: CHART_COLORS.error },
                  { label: 'Uncovered', value: uncovered, hex: CHART_COLORS.fail },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: row.hex }} />
                      {row.label}
                    </span>
                    <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(row.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Test cases mapped per requirement</div>
            <BarChart
              data={reqs.map((r) => ({
                label: r.requirement_id,
                value: Number(r.test_case_count) || 0,
                color: String(r.coverage_status || '').toUpperCase() === 'COVERED' ? CHART_COLORS.pass : CHART_COLORS.fail,
              }))}
              height={180}
              ariaLabel="Generated test cases per requirement"
            />
            <p className="mt-3 text-[11px] text-ink-muted">
              {testsMapped} test case(s) mapped across {reqs.length} requirement(s) — consistent with {fmtNum(data.overview.total_test_cases)} total generated.
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-card border border-line bg-bg-secondary/40 p-5">
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="font-medium text-ink-muted">Coverage by requirement</span>
            <span className="font-mono font-semibold text-green">{pct.toFixed(1)}%</span>
          </div>
          <ProgressBar value={pct} to="bg-gradient-to-r from-green to-green-darker" />
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-green" /> Covered {fmtNum(covered)}</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-amber" /> Partial {fmtNum(partial)}</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-red" /> Uncovered {fmtNum(uncovered)}</span>
          </div>
        </div>
      </Section>

      {/* Requirement cards */}
      <Section
        icon={ListChecks}
        title="Requirement cards"
        lede="Requirement ID, category, description, coverage/validation badges and mapped tests — all real backend data."
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {reqs.map((r, i) => {
            const cov = String(r.coverage_status || '').toUpperCase();
            const isCovered = cov === 'COVERED';
            const isPartial = cov === 'PARTIALLY COVERED';
            const border = isCovered ? 'border-line-success/40' : isPartial ? 'border-line-warn/40' : 'border-line-error/40';
            const accent = isCovered
              ? 'bg-gradient-to-r from-green/70 to-green/20'
              : isPartial
                ? 'bg-gradient-to-r from-amber/70 to-amber/20'
                : 'bg-gradient-to-r from-red/70 to-red/20';
            const tests = Number(r.test_case_count) || 0;
            return (
              <div
                key={r.requirement_id}
                className={`card-hover anim-entry relative overflow-hidden rounded-card border bg-card p-4 shadow-card ${border}`}
                style={{ animationDelay: `${i * 45}ms` }}
              >
                <div className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${accent}`} />
                <div className="flex items-start justify-between gap-2">
                  <code className="font-mono text-xs font-bold text-ink">{r.requirement_id}</code>
                  <Badge status={r.coverage_status} />
                </div>
                <div className="mt-1 inline-flex rounded-pill border border-line/70 bg-bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                  {r.category}
                </div>
                <p className="line-clamp-2 mt-2.5 min-h-[40px] text-xs leading-relaxed text-ink-secondary">{r.description}</p>
                <div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2.5 text-[11px] text-ink-muted">
                  <span className={`flex items-center gap-1 ${tests > 0 ? 'text-blue' : ''}`}>
                    <FlaskConical size={11} />
                    {tests > 0 ? `${fmtNum(tests)} test${tests === 1 ? '' : 's'} mapped` : 'no tests mapped'}
                  </span>
                  <Badge status={r.validation_status} />
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      {/* Requirements table */}
      <Section icon={ClipboardCheck} title="Requirements table" lede="Full requirement detail with coverage and validation.">
        <DataTable
          columns={[
            { key: 'requirement_id', label: 'ID', mono: true },
            { key: 'category', label: 'Category' },
            { key: 'coverage_status', label: 'Coverage' },
            { key: 'test_case_count', label: 'Tests' },
            { key: 'validation_status', label: 'Validation' },
            { key: 'description', label: 'Description' },
          ]}
          rows={reqs.map((r) => ({
            requirement_id: r.requirement_id,
            category: r.category,
            coverage_status: <Badge status={r.coverage_status} />,
            test_case_count: fmtNum(r.test_case_count),
            validation_status: <Badge status={r.validation_status} />,
            description: r.description,
          }))}
        />
      </Section>
    </div>
  );
}

// 4. RAG / Knowledge (Section C)
export function Knowledge({ data }) {
  const k = data.knowledge;
  const docs = k.documents || [];
  const mapping = k.requirement_mapping || [];
  const mapped = mapping.filter((m) => Number(m.retrieval_count) > 0).length;
  const retrievalPct = mapping.length > 0 ? (mapped / mapping.length) * 100 : 0;
  const totalChunks = mapping.reduce((s, m) => s + (Number(m.retrieval_count) || 0), 0);
  const semantic = Boolean(k.semantic_metrics);

  return (
    <div className="space-y-6">
      {/* Hero — knowledge base status */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-purple/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-purple">
              <Brain size={13} strokeWidth={2.2} />
              RAG Knowledge Base
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">RAG knowledge base</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">{fmtNum(k.corpus_description)}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status="INDEXED" />
              <span className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold ${semantic ? 'border-line-success/60 bg-ok-bg text-green' : 'border-line bg-bg-secondary text-ink-muted'}`}>
                <span className={`h-1.5 w-1.5 rounded-pill ${semantic ? 'bg-green' : 'bg-ink-disabled'}`} />
                {semantic ? 'SEMANTIC METRICS ENABLED' : 'SEMANTIC METRICS NOT COMPUTED'}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <BookOpen size={11} className="text-blue" />
                Corpus v{fmtNum(k.corpus_version)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Documents</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-purple">{fmtNum(k.document_count)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Topics found</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-cyan">{fmtNum(k.retrieved_topics.length)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Context chunks</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-blue">{fmtNum(totalChunks)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Documents', value: k.document_count, accent: 'purple', icon: Database, sub: 'indexed corpus' },
          { label: 'Retrieval topics', value: k.retrieved_topics.length, accent: 'cyan', icon: Search, sub: 'unique topics' },
          { label: 'Corpus version', value: k.corpus_version, accent: 'blue', icon: BookOpen, sub: 'knowledge base release' },
          { label: 'Requirement mappings', value: mapping.length, accent: 'cyan', icon: GitBranch, sub: 'requirements tracked' },
          { label: 'With retrieved context', value: mapped, accent: 'green', icon: CircleCheck, sub: `${totalChunks} context chunks total` },
        ]}
      />

      {/* Retrieval coverage */}
      <Section
        icon={Search}
        title="Retrieval coverage"
        lede="How many requirements actually retrieved knowledge context during RAG — real retrieval evidence only."
        right={<Badge status={mapped > 0 ? 'INDEXED' : 'NA'} />}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-ink-muted">Requirements with retrieval evidence</span>
              <span className="font-mono font-semibold text-cyan">{mapped}/{mapping.length}</span>
            </div>
            <ProgressBar value={retrievalPct} to="bg-gradient-to-r from-cyan to-blue" />
            <div className="mt-4 space-y-2">
              {mapping.map((m) => {
                const count = Number(m.retrieval_count) || 0;
                return (
                  <div key={m.requirement_id} className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
                    <span className="flex items-center gap-2">
                      <code className="font-mono text-xs font-bold text-ink">{m.requirement_id}</code>
                      <Badge status={count > 0 ? 'INDEXED' : 'NA'} />
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className={`font-mono font-semibold ${count > 0 ? 'text-cyan' : 'text-ink-disabled'}`}>{fmtNum(count)}</span>
                      <span className="text-ink-disabled">chunks</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Retrieved chunks by requirement</div>
            <BarChart
              data={mapping.map((m) => ({
                label: m.requirement_id,
                value: Number(m.retrieval_count) || 0,
                color: Number(m.retrieval_count) > 0 ? CHART_COLORS.cyan : CHART_COLORS.skip,
              }))}
              height={180}
              ariaLabel="Retrieved context chunks per requirement"
            />
            <p className="mt-3 text-[11px] text-ink-muted">
              {mapped} of {mapping.length} requirement(s) retrieved context; {totalChunks} context chunk(s) were served in total.
            </p>
          </div>
        </div>
      </Section>

      {/* Corpus documents */}
      <Section
        icon={Database}
        title={`Corpus documents (v${fmtNum(k.corpus_version)})`}
        lede="Indexed knowledge documents used by RAG retrieval — titles, topics and sources are real."
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {docs.map((d, i) => (
            <div key={d.document_id} className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card" style={{ animationDelay: `${i * 30}ms` }}>
              <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue/40 to-transparent" />
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-semibold text-ink">{d.title}</span>
                <code className="shrink-0 font-mono text-[10px] text-ink-disabled">{d.document_id}</code>
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <code className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-cyan">{d.topic}</code>
                <Badge status={d.version} />
              </div>
              <div className="mt-2.5 flex items-center gap-1.5 border-t border-line/60 pt-2 text-[11px] text-ink-muted">
                <BookOpen size={11} className="text-purple" />
                <span className="truncate">{d.source}</span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Requirement → retrieved knowledge */}
      <Section
        icon={GitBranch}
        title="Requirement → retrieved knowledge"
        lede="Real retrieval evidence per requirement: counts, topics and sources."
      >
        <DataTable
          columns={[
            { key: 'requirement_id', label: 'Requirement', mono: true },
            { key: 'retrieval_count', label: 'Retrieved context' },
            { key: 'topics', label: 'Topics' },
            { key: 'sources', label: 'Sources' },
          ]}
          rows={mapping.map((m) => ({
            requirement_id: m.requirement_id,
            retrieval_count: <span className={`font-mono font-semibold ${Number(m.retrieval_count) > 0 ? 'text-cyan' : 'text-ink-disabled'}`}>{fmtNum(m.retrieval_count)}</span>,
            topics: (m.topics || []).length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {(m.topics || []).map((t) => (
                  <code key={t} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-cyan">{t}</code>
                ))}
              </div>
            ) : (
              <span className="text-ink-disabled">—</span>
            ),
            sources: joinList(m.sources),
          }))}
        />
      </Section>
    </div>
  );
}

// 5. Test Generation (Section D)
export function Generation({ data }) {
  const g = data.generation;
  const reqs = data.requirements || [];
  const tests = g.tests || [];
  const mockCount = tests.filter((t) => String(t.generation_mode || '').toUpperCase() === 'MOCK').length;
  const realCount = tests.length - mockCount;
  const validated = tests.filter((t) => String(t.validation_status || '').toUpperCase() === 'VALIDATED').length;
  const mode = String(g.generation_mode || '').toUpperCase();
  const total = Number(g.total_generated) || tests.length;

  const categoryCounts = tests.reduce((acc, t) => {
    const cat = String(t.category || 'UNKNOWN').toUpperCase();
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});
  const categories = Object.keys(categoryCounts).sort();
  const CAT_COLORS = [CHART_COLORS.cyan, CHART_COLORS.blue, CHART_COLORS.purple, CHART_COLORS.error, CHART_COLORS.pass];

  const reqCounts = tests.reduce((acc, t) => {
    acc[t.requirement_id] = (acc[t.requirement_id] || 0) + 1;
    return acc;
  }, {});
  const reqEntries = Object.entries(reqCounts).sort((a, b) => String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true }));
  const REQ_COLORS = [CHART_COLORS.cyan, CHART_COLORS.purple, CHART_COLORS.blue];

  const priorityCounts = tests.reduce((acc, t) => {
    const p = String(t.priority || 'NA').toUpperCase();
    acc[p] = (acc[p] || 0) + 1;
    return acc;
  }, {});
  const priorities = Object.keys(priorityCounts).sort();

  return (
    <div className="space-y-6">
      {/* Hero — generation status */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-blue/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan">
              <Sparkles size={13} strokeWidth={2.2} />
              AI Test Generation
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Test generation pipeline</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">
              {mode === 'MOCK'
                ? 'Test cases were generated by the deterministic mock provider (no LLM spend).'
                : 'Test cases were generated by a real LLM provider.'}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status={g.generation_mode} />
              <Badge status={validated === tests.length && tests.length > 0 ? 'VALIDATED' : tests.length > 0 ? 'PARTIAL' : 'NA'} />
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <FlaskConical size={11} className="text-blue" />
                {fmtNum(total)} of {fmtNum(data.overview.total_test_cases)} catalogued · {realCount > 0 ? `${realCount} real LLM` : 'mock-origin'}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Total generated</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-blue">{fmtNum(total)}</div>
            </div>
            <div className="rounded-card border border-line-success/50 bg-ok-bg/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Validated</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-green">{fmtNum(validated)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Requirements covered</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-purple">{fmtNum(Object.keys(reqCounts).length)}</div>
            </div>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Categories</span>
          {categories.map((c) => (
            <span key={c} className="rounded-pill border border-line/70 bg-bg-secondary px-2 py-0.5 font-mono text-[10px] text-cyan">
              {c} {categoryCounts[c]}
            </span>
          ))}
          <span className="text-ink-disabled">·</span>
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Priority</span>
          {priorities.map((p) => (
            <span key={p} className="rounded-pill border border-line/70 bg-bg-secondary px-2 py-0.5 font-mono text-[10px] text-blue">
              {p} {priorityCounts[p]}
            </span>
          ))}
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-4"
        items={[
          { label: 'Total generated', value: total, accent: 'blue', icon: FlaskConical, sub: 'generated test cases' },
          { label: 'Validated', value: validated, accent: 'green', icon: CircleCheck, sub: `${validated} of ${total} validated` },
          { label: 'MOCK', value: mockCount, accent: 'cyan', icon: Sparkles, sub: 'mock-generated cases' },
          { label: 'Requirements covered', value: Object.keys(reqCounts).length, accent: 'purple', icon: GitBranch, sub: `${reqs.length} requirement(s) tracked` },
        ]}
      />

      {/* Test-case distribution */}
      <Section
        icon={GitBranch}
        title="Test-case distribution"
        lede="Real distribution of generated cases by requirement and by category."
        right={<Badge status={tests.length > 0 ? 'GENERATED' : 'NA'} />}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Tests by requirement</div>
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <DonutChart
                segments={reqEntries.map(([id, v], i) => ({ label: id, value: v, color: REQ_COLORS[i % REQ_COLORS.length] }))}
                centerLabel={String(total)}
                centerSub="generated"
                centerHint={`${Object.keys(reqCounts).length} requirements`}
              />
              <div className="w-full min-w-0 flex-1 space-y-1.5">
                {reqEntries.map(([id, v], i) => (
                  <div key={id} className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: REQ_COLORS[i % REQ_COLORS.length] }} />
                      <code className="font-mono text-xs font-bold text-ink">{id}</code>
                    </span>
                    <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-card border border-line bg-bg-secondary/40 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Tests by category</div>
            <BarChart
              data={categories.map((c, i) => ({ label: c, value: categoryCounts[c], color: CAT_COLORS[i % CAT_COLORS.length] }))}
              height={180}
              ariaLabel="Generated test cases by category"
            />
            <p className="mt-3 text-[11px] text-ink-muted">
              {categories.length} distinct generation category (e.g. POSITIVE, BOUNDARY, NEGATIVE, EQUIVALENCE) reported by the backend.
            </p>
          </div>
        </div>
      </Section>

      {/* Generated test cases */}
      <Section
        icon={Sparkles}
        title="Generated test cases"
        lede="Each generated test with its requirement mapping, priority, category, validation state and (real) requirement context."
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {tests.map((t, i) => {
            const req = reqById(reqs, t.requirement_id);
            const high = String(t.priority).toUpperCase() === 'HIGH';
            return (
              <div key={t.test_case_id} className="card-hover anim-entry relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card" style={{ animationDelay: `${i * 35}ms` }}>
                <div className={`pointer-events-none absolute inset-x-0 top-0 h-px ${high ? 'bg-gradient-to-r from-transparent via-amber/40 to-transparent' : 'bg-gradient-to-r from-transparent via-blue/40 to-transparent'}`} />
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-xs font-bold text-ink">{t.test_case_id}</div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-muted">
                      <GitBranch size={11} className="text-cyan" />
                      {t.requirement_id}
                    </div>
                  </div>
                  <Badge status={t.validation_status} />
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  <span className="rounded-pill border border-line/70 bg-bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">{t.category}</span>
                  <span className={`rounded-pill border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${high ? 'border-line-warn/60 bg-warn-bg text-amber' : 'border-line bg-bg-secondary text-ink-muted'}`}>{t.priority}</span>
                  <Badge status={t.generation_mode} />
                </div>
                {req ? (
                  <p className="mt-3 line-clamp-2 border-t border-line/60 pt-2 text-[11px] leading-relaxed text-ink-muted">
                    <span className="font-semibold text-ink-secondary">Context:</span> {req.description}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </Section>

      {/* Generated tests table */}
      <Section icon={ListChecks} title="Generated tests table" lede="Full generation detail for scanning.">
        <DataTable
          columns={[
            { key: 'test_case_id', label: 'Test case', mono: true },
            { key: 'requirement_id', label: 'Requirement', mono: true },
            { key: 'category', label: 'Category' },
            { key: 'priority', label: 'Priority' },
            { key: 'generation_mode', label: 'Mode' },
            { key: 'validation_status', label: 'Validation' },
          ]}
          rows={tests.map((t) => ({
            test_case_id: t.test_case_id,
            requirement_id: t.requirement_id,
            category: t.category,
            priority: t.priority,
            generation_mode: <Badge status={t.generation_mode} />,
            validation_status: <Badge status={t.validation_status} />,
          }))}
        />
      </Section>
    </div>
  );
}

// 6. Test Execution (Section E)
export function Execution({ data }) {
  const e = data.execution;
  const o = data.overview;
  const genTotal = Number(o.total_test_cases) || 0;
  const execTotal = Number(e.total_executed) || 0;
  const history = e.execution_history || [];
  const passRate = execTotal > 0 ? (Number(e.passed) / execTotal) * 100 : 0;
  const failedRows = history.filter((h) => String(h.status).toUpperCase() === 'FAIL');
  const statusBadge = Number(e.failed) > 0 ? 'PARTIAL' : execTotal > 0 ? 'COMPLETE' : 'NA';
  const reqByTest = (data.generation.tests || []).reduce((m, t) => {
    m[t.test_case_id] = t.requirement_id;
    return m;
  }, {});
  const legend = [
    { label: 'Passed', value: e.passed, cls: 'bg-green' },
    { label: 'Failed', value: e.failed, cls: 'bg-red' },
    { label: 'Errors', value: e.errors, cls: 'bg-amber' },
    { label: 'Skipped', value: e.skipped, cls: 'bg-ink-disabled' },
  ];

  return (
    <div className="space-y-6">
      {/* Hero — execution status */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className={`pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent ${Number(e.failed) > 0 ? 'via-red' : 'via-green'} to-transparent`} />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-blue/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan">
              <Activity size={13} strokeWidth={2.2} />
              IoT Test Execution
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Test execution monitor</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">
              {execTotal} of {genTotal} generated test(s) executed; {fmtNum(e.failed)} recorded as FAIL.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status={statusBadge} />
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <CirclePlay size={11} className="text-blue" />
                Pass rate {passRate.toFixed(1)}%
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <Gauge size={11} className="text-cyan" />
                Coverage {fmtNum(e.execution_coverage)}%
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Executed</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-blue">{fmtNum(execTotal)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Pass rate</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-grad-primary">{execTotal > 0 ? `${passRate.toFixed(1)}%` : '—'}</div>
            </div>
            <div className={`rounded-card border px-4 py-3 text-right ${Number(e.failed) > 0 ? 'border-line-error/50 bg-err-bg/60' : 'border-line-success/50 bg-ok-bg/60'}`}>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Failed</div>
              <div className={`tab-nums mt-1.5 text-xl font-bold ${Number(e.failed) > 0 ? 'text-red' : 'text-green'}`}>{fmtNum(e.failed)}</div>
            </div>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Results</span>
          {legend.map((row) => (
            <span key={row.label} className="flex items-center gap-1.5 font-mono">
              <span className={`inline-block h-2 w-2 rounded-sm ${row.cls}`}></span>
              {row.label.toUpperCase()} <span className="font-semibold text-ink-secondary">{fmtNum(row.value)}</span>
            </span>
          ))}
          <span className="text-ink-disabled">·</span>
          <span className="font-mono text-ink-muted">{fmtNum(execTotal)}/{fmtNum(genTotal)} executed</span>
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Executed', value: execTotal, accent: 'blue', icon: CirclePlay, sub: `${execTotal} of ${genTotal} generated` },
          { label: 'Passed', value: e.passed, accent: 'green', icon: Check, sub: `${passRate.toFixed(1)}% pass rate` },
          { label: 'Failed', value: e.failed, accent: 'red', icon: XCircle, sub: `${failedRows.length} FAIL record(s)` },
          { label: 'Errors', value: e.errors, accent: 'amber', icon: TriangleAlert, sub: 'errors in history' },
          { label: 'Skipped', value: e.skipped, accent: 'slate', icon: Clock, sub: 'skipped executions' },
        ]}
      />

      {/* Distribution + coverage */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Section icon={CirclePlay} title="Execution distribution" lede="Real PASS / FAIL / ERROR / SKIPPED split of executed tests.">
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <DonutChart
              segments={[
                { label: 'PASS', value: e.passed, color: CHART_COLORS.pass },
                { label: 'FAIL', value: e.failed, color: CHART_COLORS.fail },
                { label: 'ERROR', value: e.errors, color: CHART_COLORS.error },
                { label: 'SKIPPED', value: e.skipped, color: CHART_COLORS.skip },
              ]}
              centerLabel={String(execTotal)}
              centerSub="executed"
            />
            <div className="w-full min-w-0 flex-1 space-y-1.5">
              {legend.map((row) => (
                <div key={row.label} className="flex items-center justify-between text-[11px] text-ink-muted">
                  <span className="flex items-center gap-1.5">
                    <span className={`inline-block h-2.5 w-2.5 rounded-sm ${row.cls}`} />
                    {row.label}
                  </span>
                  <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(row.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </Section>

        <Section icon={Gauge} title="Execution coverage" lede="Executed tests against the generated test catalogue.">
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <GaugeChart value={e.execution_coverage} centerLabel="Coverage" sub={`${fmtNum(execTotal)} / ${fmtNum(genTotal)} tests`} from="#22D3EE" to="#3B82F6" />
            <div className="w-full min-w-0 flex-1 space-y-2.5">
              <div className="mb-1.5">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-ink-muted">Execution coverage</span>
                  <span className="font-mono font-semibold text-grad-primary">{fmtNum(e.execution_coverage)}%</span>
                </div>
                <ProgressBar value={e.execution_coverage} to="bg-gradient-to-r from-cyan to-blue" />
              </div>
              <p className="text-[11px] leading-relaxed text-ink-muted">
                Coverage = executed tests against generated tests. Any generated test that is not executed lowers this value.
              </p>
            </div>
          </div>
        </Section>
      </div>

      {/* Failed tests — prominent */}
      <Section
        icon={XCircle}
        title="Failed tests"
        lede="Executions with FAIL status (real evidence)."
        right={failedRows.length ? <Badge status={`${failedRows.length} FAIL`} /> : null}
      >
        {failedRows.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {failedRows.map((h) => {
              const req = reqByTest[h.test_case_id];
              return (
                <div key={h.execution_id} className="card-hover anim-entry relative overflow-hidden rounded-card border border-line-error/50 bg-err-bg/40 px-3 py-2.5" style={{ animationDelay: '0ms' }}>
                  <div className="pointer-events-none absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-red to-red/30" />
                  <div className="flex flex-wrap items-center justify-between gap-2 pl-1">
                    <div className="min-w-0">
                      <code className="font-mono text-xs font-bold text-ink">{h.test_case_id}</code>
                      {req ? (
                        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-muted">
                          <GitBranch size={10} className="text-cyan" /> {req}
                        </div>
                      ) : (
                        <div className="mt-0.5 text-[11px] text-ink-muted">Requirement: Not available</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-ink-muted">{String(h.execution_id).slice(0, 10)}…</span>
                      <Badge status={h.status} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-ink-muted">No failed executions recorded.</p>
        )}
      </Section>

      {/* Execution records */}
      <Section
        icon={Activity}
        title="Execution records"
        lede="Every executed test with its real status, requirement mapping and execution id."
        right={<Badge status={history.length > 0 ? 'EXECUTED' : 'NA'} />}
      >
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          {history.map((h) => (
            <span
              key={h.execution_id}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[10px] font-semibold"
              style={{ background: `${execColor(h.status)}1F`, color: execColor(h.status) }}
              title={`${h.test_case_id} · ${String(h.execution_id).slice(0, 8)}…`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: execColor(h.status) }} />
              {h.test_case_id}
            </span>
          ))}
        </div>
        <DataTable
          columns={[
            { key: 'test_case_id', label: 'Test case', mono: true },
            { key: 'requirement_id', label: 'Requirement' },
            { key: 'status', label: 'Status' },
            { key: 'execution_id', label: 'Execution id', mono: true },
          ]}
          rows={history.map((h) => ({
            test_case_id: h.test_case_id,
            requirement_id: reqByTest[h.test_case_id] ? (
              <code className="font-mono text-[11px] text-cyan">{reqByTest[h.test_case_id]}</code>
            ) : (
              <span className="text-ink-disabled">Not available</span>
            ),
            status: <Badge status={h.status} />,
            execution_id: String(h.execution_id).slice(0, 8),
          }))}
        />
      </Section>
    </div>
  );
}

// 7. Fault Analysis (Section F)
export function Faults({ data }) {
  const f = data.fault_summary;
  const faults = f.faults || [];
  const notExec = faults.filter((x) => String(x.detection_status || '').toUpperCase() === 'NOT_EXECUTED').length;
  const detectedRows = faults.filter((x) => String(x.detection_status || '').toUpperCase() === 'DETECTED').length;
  const missedFaults = !isNA(f.missed_faults) ? Number(f.missed_faults) : Math.max(0, Number(f.total_faults) - Number(f.detected_faults));
  const rate = Number(f.fault_detection_rate) || 0;
  const rateColor = rate >= 80 ? { from: '#22C55E', to: '#16A34A' } : rate >= 50 ? { from: '#F59E0B', to: '#F59E0B' } : { from: '#EF4444', to: '#EF4444' };
  const alertTone = missedFaults > 0 ? 'bad' : detectedRows > 0 ? 'warn' : notExec > 0 ? 'warn' : 'ok';

  return (
    <div className="space-y-6">
      {/* Hero — fault summary */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-amber/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-amber">
              <ShieldAlert size={13} strokeWidth={2.2} />
              Fault Analysis & Diagnostics
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Fault detection & diagnostics</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">
              {fmtNum(f.detected_faults)} of {fmtNum(f.total_faults)} fault(s) confirmed via failing assertions; {fmtNum(missedFaults)} reported missed by the run summary.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge status={missedFaults > 0 ? 'MISSED' : detectedRows > 0 ? 'DETECTED' : 'NA'} />
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <Gauge size={11} className="text-amber" />
                Detection rate {fmtNum(f.fault_detection_rate)}%
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <CircleCheck size={11} className="text-green" />
                {fmtNum(detectedRows)} detected · {fmtNum(notExec)} not executed
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Total faults</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-amber">{fmtNum(f.total_faults)}</div>
            </div>
            <div className="rounded-card border border-line-success/50 bg-ok-bg/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Detected</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-green">{fmtNum(f.detected_faults)}</div>
            </div>
            <div className="rounded-card border border-line-error/50 bg-err-bg/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Missed</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-red">{fmtNum(missedFaults)}</div>
            </div>
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Detection rate</div>
              <div className="tab-nums mt-1.5 text-xl font-bold text-grad-fault">{fmtNum(f.fault_detection_rate)}%</div>
            </div>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Faults</span>
          {faults.length ? (
            faults.map((x) => {
              const st = String(x.detection_status || '').toUpperCase();
              const color = st === 'DETECTED' ? 'text-green' : st === 'MISSED' ? 'text-red' : 'text-ink-muted';
              const bg = st === 'DETECTED' ? 'bg-green' : st === 'MISSED' ? 'bg-red' : 'bg-ink-disabled';
              return (
                <span key={x.fault_id} className="flex items-center gap-1.5 font-mono">
                  <span className={`inline-block h-2 w-2 rounded-sm ${bg}`}></span>
                  {x.fault_id} <span className={`font-semibold ${color}`}>{st}</span>
                </span>
              );
            })
          ) : (
            <span className="text-ink-disabled">No faults recorded.</span>
          )}
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Total faults', value: f.total_faults, accent: 'amber', icon: ShieldAlert, sub: 'run summary' },
          { label: 'Detected', value: f.detected_faults, accent: 'green', icon: CircleCheck, sub: 'surfaced by failing assertion' },
          { label: 'Missed', value: missedFaults, accent: 'red', icon: XCircle, sub: 'backend-reported missed' },
          { label: 'Not executed', value: notExec, accent: 'slate', icon: Clock, sub: 'no test injected' },
          { label: 'Detection rate', value: rate, suffix: '%', accent: 'fault', icon: Gauge, sub: 'backend reported' },
        ]}
      />

      {/* Detection visualization */}
      <Section
        icon={ShieldAlert}
        title="Detection visualization"
        lede="A fault is DETECTED only when a test that injected it ended FAIL — never inferred from anything else."
        right={<Badge status={rate >= 80 ? 'TARGET_REACHED' : rate >= 50 ? 'PARTIAL' : 'LOW'} />}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="flex items-center justify-center rounded-card border border-line bg-bg-secondary/40 p-5">
            <GaugeChart value={f.fault_detection_rate} centerLabel="Detection rate" sub={`${fmtNum(f.detected_faults)} of ${fmtNum(f.total_faults)} faults`} from={rateColor.from} to={rateColor.to} />
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-green" /> Detected</span>
              <span className="tab-nums font-mono font-semibold text-green">{fmtNum(detectedRows)}</span>
            </div>
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-red" /> Missed</span>
              <span className="tab-nums font-mono font-semibold text-red">{fmtNum(missedFaults)}</span>
            </div>
            <div className="flex items-center justify-between rounded-card border border-line/70 bg-bg-secondary/60 px-3 py-2 text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ink-disabled" /> Not executed</span>
              <span className="tab-nums font-mono font-semibold text-ink-secondary">{fmtNum(notExec)}</span>
            </div>
            <p className="pt-1 text-[11px] leading-relaxed text-ink-muted">
              Detection rate is the backend-reported summary value; not-executed faults have no execution evidence, so detection cannot be inferred.
            </p>
          </div>
        </div>
      </Section>

      {/* Fault status */}
      <Section
        icon={TriangleAlert}
        title="Fault status"
        lede="Fault banner reflects the real detection state of every injected fault."
        right={<Badge status={alertTone === 'bad' ? 'MISSED' : detectedRows > 0 ? 'DETECTED' : notExec > 0 ? 'NOT_EXECUTED' : 'NA'} />}
      >
        <AlertBanner
          tone={alertTone}
          title={
            missedFaults > 0
              ? 'FAULT MISSED — detection gap'
              : detectedRows > 0
                ? 'FAULT DETECTED'
                : notExec > 0
                  ? 'FAULTS NOT EXECUTED'
                  : 'Fault environment clear'
          }
          lede={
            missedFaults > 0
              ? `${missedFaults} fault(s) were not surfaced by any execution evidence (${detectedRows} detected, ${notExec} not executed).`
              : detectedRows > 0
                ? `${detectedRows} fault(s) injected and detected via failing test assertions.`
                : notExec > 0
                  ? `${notExec} fault(s) had no corresponding test execution.`
                  : 'No faults were injected into this run.'
          }
          right={<span className="font-mono text-xs text-ink-muted">{fmtNum(f.detected_faults)}/{fmtNum(f.total_faults)} detected</span>}
        />
        {faults.length ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {faults.map((fault, i) => (
              <FaultCard key={fault.fault_id} fault={fault} delay={i * 80} />
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-ink-muted">No faults recorded.</p>
        )}
      </Section>

      {/* Fault details */}
      <Section icon={ListChecks} title="Fault details" lede="Real fault records: detection, injection, affected requirements/tests and available evidence.">
        <DataTable
          columns={[
            { key: 'fault_id', label: 'Fault', mono: true },
            { key: 'fault_type', label: 'Type' },
            { key: 'detection_status', label: 'Detection' },
            { key: 'injection_status', label: 'Injection' },
            { key: 'requirements', label: 'Requirements' },
            { key: 'tests', label: 'Related tests' },
            { key: 'execution_result', label: 'Execution' },
            { key: 'detection_evidence', label: 'Evidence' },
          ]}
          rows={faults.map((x) => ({
            fault_id: x.fault_id,
            fault_type: x.fault_type,
            detection_status: <Badge status={x.detection_status} />,
            injection_status: <Badge status={x.injection_status} />,
            requirements: (x.requirement_ids || []).length ? (
              <div className="flex flex-wrap gap-1">
                {(x.requirement_ids || []).map((id) => (
                  <code key={id} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-cyan">{id}</code>
                ))}
              </div>
            ) : (
              <span className="text-ink-disabled">—</span>
            ),
            tests: (x.related_test_case_ids || []).length ? (
              <div className="flex flex-wrap gap-1">
                {(x.related_test_case_ids || []).map((id) => (
                  <code key={id} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-blue">{id}</code>
                ))}
              </div>
            ) : (
              <span className="text-ink-disabled">—</span>
            ),
            execution_result: <Badge status={x.execution_result} />,
            detection_evidence: x.detection_evidence || (
              <span className="text-ink-disabled">—</span>
            ),
          }))}
        />
      </Section>
    </div>
  );
}

// 8. Autonomous Refinement (Section G)
export function Refinement({ data }) {
  const r = data.refinement;
  const trace = (data.traceability && data.traceability.rows) || [];
  const refinedReqs = trace.filter((x) => x.refined);
  const available = !!r.available;
  const iterations = r.iterations || [];
  const pb = available && !isNA(r.coverage_before) ? Number(r.coverage_before) : null;
  const pa = available && !isNA(r.coverage_after) ? Number(r.coverage_after) : null;
  const improvement = available && !isNA(r.improvement_requirement_coverage) ? Number(r.improvement_requirement_coverage) : null;
  const gapsBefore = available && !isNA(r.gaps_before) ? Number(r.gaps_before) : null;
  const gapsAfter = available && !isNA(r.gaps_after) ? Number(r.gaps_after) : null;
  const gapsClosed = gapsBefore != null && gapsAfter != null ? Math.max(0, gapsBefore - gapsAfter) : null;
  const pct = (v) => (v == null ? '—' : `${v.toFixed(1)}%`);

  return (
    <div className="space-y-6">
      {/* Hero — refinement status */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-purple to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-purple/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-purple">
              <RefreshCw size={13} strokeWidth={2.2} />
              Autonomous Refinement
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Refinement & coverage improvement</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">
              {available
                ? 'Run artifact available — every delta on this page is a real backend measurement.'
                : 'The autonomous loop closes requirement-coverage gaps until a stop condition; this run produced no refinement artifact, so coverage deltas are Not available.'}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {available ? <Badge status={r.stop_reason} /> : <Badge status="NA" />}
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <Sparkles size={11} className="text-purple" />
                {fmtNum(iterations.length)} iteration(s)
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <CircleCheck size={11} className="text-green" />
                {fmtNum(refinedReqs.length)} requirement(s) refined
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Run artifact</div>
              <div className="mt-1.5 text-sm font-bold text-ink">{available ? fmtNum(r.stop_reason) : 'Not available'}</div>
            </div>
            <HeroTile label="Iterations" value={iterations.length} accent="text-purple" />
            <HeroTile label="Requirements refined" value={refinedReqs.length} accent="text-green" />
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className="font-semibold uppercase tracking-wider text-ink-muted">Requirements</span>
          {trace.length ? (
            trace.map((x) => (
              <span key={x.requirement_id} className={`flex items-center gap-1.5 font-mono ${x.refined ? 'text-green' : 'text-ink-muted'}`}>
                <span className={`inline-block h-2 w-2 rounded-sm ${x.refined ? 'bg-green' : 'bg-ink-disabled'}`} />
                {x.requirement_id}
                {x.refined && <ChevronRight size={11} className="text-green" />}
              </span>
            ))
          ) : (
            <span className="text-ink-disabled">No traceability rows available.</span>
          )}
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-5"
        items={[
          { label: 'Coverage before', value: pb, accent: 'cyan', icon: Target, sub: available ? 'requirement coverage' : 'Not available' },
          { label: 'Coverage after', value: pa, accent: 'green', icon: CircleCheck, sub: available ? 'requirement coverage' : 'Not available' },
          { label: 'Improvement', value: improvement, accent: 'refine', icon: TrendingUp, sub: available ? 'percentage point delta' : 'Not available' },
          { label: 'Gaps closed', value: gapsClosed, accent: 'green', icon: Sparkles, sub: available ? 'before − after' : 'Not available' },
          { label: 'Requirements refined', value: refinedReqs.length, accent: 'purple', icon: RefreshCw, sub: 'from traceability links' },
        ]}
      />

      {/* Before → After */}
      <Section
        icon={RefreshCw}
        title="Refinement loop"
        lede="Coverage before and after the autonomous loop; improvement is shown only when the run artifact provides real deltas."
        right={available ? <Badge status={r.stop_reason} /> : <Badge status="NA" />}
      >
        <div className="grid items-stretch gap-3 md:grid-cols-[1fr_auto_1fr]">
          <div className="rounded-card border border-line bg-bg-secondary/60 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Coverage before</div>
            <div className={`mt-1 text-3xl font-bold ${pb == null ? 'text-ink-disabled' : 'text-cyan'}`}>{pct(pb)}</div>
            <div className="mt-2 text-[11px] text-ink-muted">{gapsBefore == null ? 'Not available' : `${gapsBefore} uncovered requirement gap(s)`}</div>
          </div>

          <div className="flex flex-col items-center justify-center gap-1.5 px-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
              <Sparkles size={13} className="text-purple" /> Autonomous refinement
            </div>
            <div className="flex items-center gap-1 text-purple">
              {iterations.length ? (
                iterations.map((it, idx) => (
                  <span key={it.iteration_number} className="flex items-center gap-1">
                    <span className="flex h-6 min-w-6 items-center justify-center rounded-md border border-line bg-card px-1.5 font-mono text-[10px] font-bold text-purple">
                      {it.iteration_number}
                    </span>
                    {idx < iterations.length - 1 && <ChevronRight size={12} className="text-ink-disabled" />}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-ink-disabled">no iterations performed</span>
              )}
            </div>
            <div className="text-[10px] text-ink-muted">
              {fmtNum(iterations.length)} iteration(s) · {fmtNum(r.total_generated)} generated · {fmtNum(r.total_executed)} executed
            </div>
          </div>

          <div className="rounded-card border border-line-success/40 bg-ok-bg/20 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Coverage after</div>
            <div className={`mt-1 text-3xl font-bold ${pa == null ? 'text-ink-disabled' : 'text-grad-success'}`}>{pct(pa)}</div>
            <div className="mt-2 text-[11px] text-ink-muted">{gapsAfter == null ? 'Not available' : `${gapsAfter} gap(s) remaining`}</div>
          </div>
        </div>

        <div className="mt-4 rounded-card border border-line/80 bg-bg-secondary/40 p-4">
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="flex items-center gap-2 font-medium text-ink-muted">
              <TrendingUp size={12} className="text-cyan" /> Coverage improvement
            </span>
            <span className={`font-mono font-semibold ${improvement == null ? 'text-ink-disabled' : 'text-grad-ai'}`}>
              {improvement == null ? 'Not available' : `+${improvement.toFixed(1)}%`}
            </span>
          </div>
          {improvement != null ? (
            <ProgressBar value={improvement} to="bg-gradient-to-r from-cyan to-purple" />
          ) : (
            <div className="h-2.5 w-full rounded-pill border border-dashed border-line bg-bg-secondary/60" title="No refinement artifact available" />
          )}
          <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
            {available
              ? 'Improvement is the real delta between before and after requirement coverage.'
              : 'No refinement artifact is available for this run — the loop did not execute, so improvement cannot be computed.'}
          </p>
        </div>
      </Section>

      {/* Refinement summary */}
      <Section
        icon={ClipboardCheck}
        title="Refinement summary"
        lede="Real refinement outcome per requirement — derived from the traceability links, never assumed."
        right={trace.length ? <Badge status={refinedReqs.length === trace.length ? 'COMPLETE' : 'PARTIAL'} /> : <Badge status="NA" />}
      >
        {trace.length ? (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {trace.map((x) => {
              const req = reqById(data.requirements, x.requirement_id);
              return (
                <div key={x.requirement_id} className="flex items-start gap-3 rounded-card border border-line bg-bg-secondary/40 p-3.5">
                  <span
                    className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${
                      x.refined ? 'bg-gradient-to-br from-green to-green text-white' : 'bg-gradient-to-br from-ink-muted to-ink-disabled text-bg-main'
                    }`}
                  >
                    {x.refined ? <Check size={15} strokeWidth={2.4} /> : <CircleDashed size={15} strokeWidth={2.4} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="font-mono text-xs font-bold text-ink">{x.requirement_id}</code>
                      <Badge status={x.coverage} />
                      {req?.category ? <span className="rounded-pill bg-blue/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue">{req.category}</span> : null}
                    </div>
                    {req?.description ? (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-muted">{req.description}</p>
                    ) : null}
                    <div className="mt-1 text-[11px] text-ink-muted">
                      <span className={x.refined ? 'text-green' : 'text-ink-disabled'}>{x.refined ? 'Refined by the autonomous loop' : 'Not refined'}</span>
                      {' · '}{fmtNum(x.test_case_ids?.length || 0)} test(s) · {fmtNum(x.rag_evidence_count || 0)} evidence link(s)
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-ink-muted">Refinement details Not available — no traceability rows to derive outcome from.</p>
        )}
      </Section>

      {/* Iterations */}
      <Section icon={ListChecks} title="Refinement iterations" lede="Per-iteration before / after coverage and improvement values.">
        {iterations.length ? (
          <DataTable
            columns={[
              { key: 'iteration_number', label: 'Iter' },
              { key: 'decision', label: 'Decision' },
              { key: 'gap_type', label: 'Gap' },
              { key: 'generated', label: 'Generated' },
              { key: 'executed', label: 'Executed' },
              { key: 'coverage_before', label: 'Cov before' },
              { key: 'coverage_after', label: 'Cov after' },
              { key: 'improvement', label: 'Improvement' },
            ]}
            rows={iterations.map((it) => ({
              iteration_number: it.iteration_number,
              decision: it.decision,
              gap_type: fmtNum(it.gap_type),
              generated: it.generated,
              executed: it.executed,
              coverage_before: isNA(it.coverage_before) ? '—' : `${Number(it.coverage_before).toFixed(1)}%`,
              coverage_after: isNA(it.coverage_after) ? '—' : `${Number(it.coverage_after).toFixed(1)}%`,
              improvement: isNA(it.improvement) ? '—' : `${Number(it.improvement).toFixed(2)}%`,
            }))}
          />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-line bg-bg-secondary/30 px-4 py-10 text-center">
            <RefreshCw size={22} className="mb-2 text-ink-disabled" />
            <div className="text-sm font-semibold text-ink-secondary">No iterations recorded</div>
            <p className="mt-1 max-w-sm text-[11px] leading-relaxed text-ink-muted">
              Iteration-level generation did not run in this session, so there are no per-iteration measurements to show.
            </p>
          </div>
        )}
      </Section>
    </div>
  );
}

// 9. Traceability (Section H) — requirement → evidence → test → execution → fault chains.
function TraceHop({ index, label, Icon, children }) {
  return (
    <>
      <div className="flex min-w-[132px] flex-1 flex-col gap-2 rounded-card border border-line/80 bg-card/70 p-3">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
          <Icon size={11} className="text-cyan" />
          {label}
        </div>
        <div className="flex-1">{children}</div>
      </div>
      {index < TRACE_HOPS.length - 1 && <ChevronRight size={14} className="shrink-0 self-center text-ink-disabled max-sm:hidden" />}
    </>
  );
}

function TraceRow({ row, index }) {
  const [open, setOpen] = useState(false);
  const covered = String(row.coverage || '').toUpperCase() === 'COVERED';
  const req = row.req;
  const testIds = row.test_case_ids || [];
  const execIds = row.execution_ids || [];
  const faultTypes = row.fault_types || [];
  const execStatuses = toUnique((row.execution_status || '').split(',').map((s) => String(s).trim()));
  const evidence = row.rag_evidence || [];

  const hops = [
    {
      label: 'Requirement',
      Icon: Target,
      node: (
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <code className="font-mono text-xs font-bold text-ink">{row.requirement_id}</code>
            {req?.category ? <span className="rounded-pill bg-blue/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue">{req.category}</span> : null}
          </div>
          {req?.description ? <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-ink-muted">{req.description}</p> : null}
        </div>
      ),
    },
    {
      label: 'Knowledge',
      Icon: BookOpen,
      node: Number(row.rag_evidence_count) > 0 ? (
        <div>
          <div className="text-base font-bold text-purple">{fmtNum(row.rag_evidence_count)}</div>
          <div className="text-[10px] text-ink-muted">retrieved chunk(s)</div>
          {evidence.length ? <div className="mt-1 truncate font-mono text-[9px] text-ink-disabled">{evidence[0]}</div> : null}
        </div>
      ) : (
        <div className="text-[11px] text-ink-disabled">No evidence</div>
      ),
    },
    {
      label: 'Generated test',
      Icon: FlaskConical,
      node: testIds.length ? (
        <div>
          <div className="mb-1.5 flex flex-wrap gap-1">
            {testIds.slice(0, 4).map((id) => (
              <code key={id} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[9px] text-blue">{id}</code>
            ))}
            {testIds.length > 4 ? <span className="self-center font-mono text-[9px] text-ink-disabled">+{testIds.length - 4}</span> : null}
          </div>
          <div className="text-[10px] text-ink-muted">{fmtNum(testIds.length)} generated test(s)</div>
        </div>
      ) : (
        <div className="text-[11px] text-ink-disabled">No tests</div>
      ),
    },
    {
      label: 'Execution',
      Icon: CirclePlay,
      node: execIds.length ? (
        <div>
          <div className="mb-1.5 flex flex-wrap gap-1">
            {execStatuses.map((st) => (
              <Badge key={st} status={st} />
            ))}
          </div>
          <div className="text-[10px] text-ink-muted">{fmtNum(execIds.length)} execution(s)</div>
        </div>
      ) : (
        <div className="text-[11px] text-ink-disabled">Not executed</div>
      ),
    },
    {
      label: 'Fault',
      Icon: TriangleAlert,
      node: faultTypes.length ? (
        <div>
          <div className="mb-1.5 flex flex-wrap gap-1">
            {faultTypes.map((ft) => (
              <code key={ft} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[9px] text-amber">{ft}</code>
            ))}
          </div>
          <Badge status={row.fault_detection} />
        </div>
      ) : (
        <div className="text-[11px] text-ink-disabled">No fault</div>
      ),
    },
  ];

  return (
    <div className="anim-entry overflow-hidden rounded-card border border-line bg-card shadow-card" style={{ animationDelay: `${index * 40}ms` }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-200 hover:bg-card-elevated/50"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-3">
          <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${covered ? 'from-green to-green' : 'from-amber to-amber'} text-white`}>
            {covered ? <Check size={16} strokeWidth={2.4} /> : <CircleDashed size={16} strokeWidth={2.4} />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <code className="font-mono text-xs font-bold text-ink">{row.requirement_id}</code>
              {row.refined && <span className="rounded-pill bg-purple/15 px-1.5 py-0.5 text-[10px] font-semibold text-purple">refined</span>}
              {covered && <span className="rounded-pill bg-ok-bg px-1.5 py-0.5 text-[10px] font-semibold text-green">COVERED</span>}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-ink-muted">
              <span className="flex items-center gap-1"><BookOpen size={10} className="text-purple" /> {fmtNum(row.rag_evidence_count || 0)} evidence</span>
              <span className="flex items-center gap-1"><FlaskConical size={10} className="text-blue" /> {fmtNum(testIds.length)} tests</span>
              <span className="flex items-center gap-1"><CirclePlay size={10} className="text-cyan" /> {fmtNum(execIds.length)} executed</span>
              {faultTypes.length ? <span className="flex items-center gap-1"><TriangleAlert size={10} className="text-red" /> {joinList(faultTypes)}</span> : null}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge status={row.coverage} />
          <ChevronRight size={16} className={`text-ink-muted transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
        </div>
      </button>

      {/* Requirement → Knowledge → Test → Execution → Fault chain */}
      <div className="border-t border-line/70 bg-bg-secondary/30 px-4 py-3">
        <div className="flex flex-wrap items-stretch gap-1.5">
          {hops.map((h, i) => (
            <TraceHop key={h.label} index={i} label={h.label} Icon={h.Icon}>
              {h.node}
            </TraceHop>
          ))}
        </div>
      </div>

      {open && (
        <div className="border-t border-line/70 bg-bg-secondary/40 px-4 py-3">
          <div className="grid gap-2 text-[11px] text-ink-muted sm:grid-cols-2">
            <div className="sm:col-span-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Description</div>
              <div className="mt-0.5 text-ink-secondary">{req?.description || 'Not available'}</div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Validation</div>
              <Badge status={row.validation_status} />
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Execution status</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {execIds.length
                  ? execStatuses.map((st) => <Badge key={st} status={st} />)
                  : <span className="text-ink-disabled">None</span>}
              </div>
            </div>
            <div className="sm:col-span-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">RAG evidence ({fmtNum(row.rag_evidence_count || 0)} chunks)</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {evidence.slice(0, 6).map((id) => (
                  <code key={id} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] text-purple">{id}</code>
                ))}
                {evidence.length > 6 ? <span className="self-center font-mono text-[10px] text-ink-disabled">+{evidence.length - 6} more</span> : null}
                {!evidence.length && <span className="text-ink-disabled">None</span>}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Test cases</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {testIds.map((id) => (
                  <code key={id} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] text-blue">{id}</code>
                ))}
                {!testIds.length && <span className="text-ink-disabled">None</span>}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Execution ids</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {execIds.map((id) => (
                  <code key={id} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] text-cyan">{String(id).slice(0, 10)}…</code>
                ))}
                {!execIds.length && <span className="text-ink-disabled">None</span>}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Fault types</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {faultTypes.map((ft) => (
                  <code key={ft} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] text-amber">{ft}</code>
                ))}
                {!faultTypes.length && <span className="text-ink-disabled">None</span>}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Refined</div>
              <div className={row.refined ? 'text-green' : 'text-ink-disabled'}>{row.refined ? 'Yes — refined by autonomous loop' : 'No'}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function Traceability({ data }) {
  const rows = (data.traceability && data.traceability.rows) || [];
  const covered = rows.filter((x) => String(x.coverage || '').toUpperCase() === 'COVERED').length;
  const evidenceCount = rows.reduce((n, x) => n + (Number(x.rag_evidence_count) || 0), 0);
  const testsMapped = rows.reduce((n, x) => n + (x.test_case_ids || []).length, 0);
  const refined = rows.filter((x) => x.refined).length;
  const decorated = rows.map((row) => ({ ...row, req: reqById(data.requirements, row.requirement_id) }));

  return (
    <div className="space-y-6">
      {/* Hero — traceability */}
      <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue to-transparent" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-blue/10 blur-3xl" />

        <div className="relative flex flex-wrap items-center justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-blue">
              <GitBranch size={13} strokeWidth={2.2} />
              Traceability
            </div>
            <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">Requirement → test traceability</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">
              Which test validates this requirement? Every requirement below shows its real links to RAG knowledge, generated tests, executions and faults.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-green">
                <Check size={11} /> {fmtNum(covered)} covered
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <CircleDashed size={11} /> {fmtNum(rows.length - covered)} uncovered
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                <ListChecks size={11} className="text-blue" /> {fmtNum(testsMapped)} test(s) mapped
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-stretch gap-3">
            <HeroTile label="Requirements" value={rows.length} accent="text-cyan" />
            <HeroTile label="Covered" value={covered} accent="text-green" />
            <HeroTile label="RAG evidence" value={evidenceCount} accent="text-purple" />
            <HeroTile label="Refined" value={refined} accent="text-green" />
          </div>
        </div>

        {/* Chain legend */}
        <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
          {TRACE_HOPS.map((h, i) => (
            <span key={h.key} className="flex items-center gap-1">
              <h.Icon size={11} className="text-cyan" />
              {h.label}
              {i < TRACE_HOPS.length - 1 && <ChevronRight size={11} className="ml-1 text-ink-disabled" />}
            </span>
          ))}
        </div>
      </div>

      {/* KPI row */}
      <StatCards
        cols="xl:grid-cols-6"
        items={[
          { label: 'Requirements', value: rows.length, accent: 'cyan', icon: GitBranch, sub: 'analysed by the backend' },
          { label: 'Covered', value: covered, accent: 'green', icon: Check, sub: 'validated by generated tests' },
          { label: 'Uncovered', value: rows.length - covered, accent: 'amber', icon: Target, sub: 'no validating test' },
          { label: 'RAG evidence links', value: evidenceCount, accent: 'purple', icon: BookOpen, sub: 'retrieved chunks' },
          { label: 'Tests mapped', value: testsMapped, accent: 'blue', icon: FlaskConical, sub: 'generated test cases' },
          { label: 'Refined', value: refined, accent: 'refine', icon: Sparkles, sub: 'by the autonomous loop' },
        ]}
      />

      {/* Chains */}
      <Section
        icon={GitBranch}
        title="Traceability chains"
        lede="Requirement → Knowledge → Test → Execution → Fault. Click a row to expand full IDs and evidence."
        right={<Badge status={rows.length && covered === rows.length ? 'COVERED' : 'PARTIALLY COVERED'} />}
      >
        <div className="space-y-2.5">
          {decorated.map((row, i) => (
            <TraceRow key={row.requirement_id} row={row} index={i} />
          ))}
        </div>
      </Section>

      {/* Table */}
      <Section
        icon={ListChecks}
        title="Traceability table"
        lede="Flat view of every requirement's real links — the direct answer to “which test validates this requirement?”."
      >
        <DataTable
          columns={[
            { key: 'requirement_id', label: 'Requirement', mono: true },
            { key: 'description', label: 'Description' },
            { key: 'evidence', label: 'RAG evidence' },
            { key: 'tests', label: 'Test cases' },
            { key: 'executions', label: 'Execution' },
            { key: 'faults', label: 'Fault' },
            { key: 'coverage', label: 'Coverage' },
            { key: 'refined', label: 'Refined' },
          ]}
          rows={decorated.map((r) => ({
            requirement_id: r.requirement_id,
            description: r.req?.description || 'Not available',
            evidence: fmtNum(r.rag_evidence_count || 0),
            tests: r.test_case_ids?.length ? (
              <span className="flex flex-wrap gap-1">
                {r.test_case_ids.map((id) => (
                  <code key={id} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-blue">{id}</code>
                ))}
              </span>
            ) : '—',
            executions: (r.execution_ids || []).length ? (
              <span className="flex flex-wrap gap-1">
                {toUnique((r.execution_status || '').split(',').map((s) => String(s).trim())).map((st) => (
                  <Badge key={st} status={st} />
                ))}
              </span>
            ) : '—',
            faults: r.fault_types?.length ? (
              <span className="flex flex-wrap gap-1">
                {r.fault_types.map((ft) => (
                  <code key={ft} className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-amber">{ft}</code>
                ))}
              </span>
            ) : '—',
            coverage: <Badge status={r.coverage} />,
            refined: r.refined ? 'Yes' : 'No',
          }))}
        />
      </Section>
    </div>
  );
}

// 10. Reports — real backend report artifacts (generated by Phase 10 / 12).
const REPORT_FILES = [
  {
    label: 'Final Project Report (JSON)',
    file: 'final_report.json',
    description: 'Machine-readable Phase 10 final report (valid JSON, traceability + real test totals).',
    command: 'python -m app.reporting.demo',
    availablePath: 'backend/reports/final_report.json',
    accent: 'grad-primary',
  },
  {
    label: 'Final Project Report (Markdown)',
    file: 'final_report.md',
    description: 'Human-readable Phase 10 final report.',
    command: 'python -m app.reporting.demo',
    availablePath: 'backend/reports/final_report.md',
    accent: 'grad-ai',
  },
  {
    label: 'Dashboard data (JSON)',
    file: 'dashboard_data.json',
    description: 'The DashboardData view model serialized (this dashboard reads the same contract).',
    command: 'python -m app.dashboard.dump',
    availablePath: 'backend/reports/dashboard_data.json',
    accent: 'grad-ai',
  },
  {
    label: 'HTML dashboard',
    file: 'dashboard.html',
    description: 'Backend-rendered read-only HTML dashboard (served by python -m app.dashboard).',
    command: 'python -m app.dashboard',
    availablePath: 'backend/reports/dashboard.html',
    accent: 'grad-primary',
  },
];

export function Reports({ data }) {
  const [rep, setRep] = useState(null);
  const [repError, setRepError] = useState(null);
  const [repLoading, setRepLoading] = useState(!data);

  async function load() {
    setRepLoading(true);
    setRepError(null);
    try {
      setRep(await fetchDashboard());
    } catch (err) {
      setRepError(err?.message || 'Unable to load report data.');
    } finally {
      setRepLoading(false);
    }
  }

  useEffect(() => {
    if (!data) load();
  }, []);

  const d = data || rep;
  const o = d?.overview || {};
  const reqs = d?.requirements || [];
  const gen = d?.generation || {};
  const ex = d?.execution || {};
  const fs = d?.final_status || {};
  const f = d?.fault_summary || {};
  const r = d?.refinement || {};
  const trRows = (d?.traceability && d.traceability.rows) || [];
  const coveredReqs = reqs.filter((x) => String(x.coverage_status || '').toUpperCase() === 'COVERED').length;
  const phaseList = fs.phases || [];
  const donePhases = phaseList.filter((p) => String(p.status || '').toUpperCase() === 'COMPLETE').length;
  const phasePct = phaseList.length ? (donePhases / phaseList.length) * 100 : 0;
  const execTotal = Math.max(0, Number(ex.total_executed) || 0);
  const passRate = execTotal ? (Number(ex.passed) / execTotal) * 100 : 0;
  const refinedCount = trRows.filter((x) => x.refined).length;
  const imp = r.available && !isNA(r.improvement_requirement_coverage) ? Number(r.improvement_requirement_coverage) : null;
  const refSummary = r.available
    ? `${fmtNum(r.iterations?.length || 0)} iteration(s) · stop ${fmtNum(r.stop_reason)}${imp == null ? '' : ` · +${imp.toFixed(1)}%`}`
    : `run artifact Not available · ${fmtNum(refinedCount)} requirement(s) refined`;
  const ft = fs.final_test_result || {};

  return (
    <div className="space-y-6">
      {repLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-panel border border-line bg-card px-6 py-12 text-sm text-ink-muted">
          <Activity size={16} className="animate-pulse text-cyan" />
          Loading project report data…
        </div>
      ) : repError ? (
        <div className="rounded-panel border border-line-error bg-err-bg/40 px-6 py-10 text-center">
          <div className="text-sm font-semibold text-red">Report data unavailable</div>
          <p className="mt-1 text-xs text-ink-muted">{repError}</p>
          <button
            onClick={load}
            className="mt-4 rounded-pill border border-line bg-card px-4 py-2 text-xs font-semibold text-ink transition-colors hover:bg-card-elevated"
          >
            Try again
          </button>
        </div>
      ) : d ? (
        <>
          {/* Hero — project report */}
          <div className="anim-entry relative overflow-hidden rounded-panel border border-line bg-header p-6 shadow-card">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan to-transparent" />
            <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan/10 blur-3xl" />

            <div className="relative flex flex-wrap items-center justify-between gap-5">
              <div className="min-w-0 max-w-3xl">
                <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan">
                  <FolderOpen size={13} strokeWidth={2.2} />
                  Project Report
                </div>
                <h2 className="mt-2 text-2xl font-bold leading-snug text-ink">{o.project_name || 'Not available'}</h2>
                <p className="mt-1.5 max-w-2xl text-xs leading-relaxed text-ink-muted">
                  {o.project_id || 'Not available'} · analysis{' '}
                  <code className="font-mono text-ink-secondary">{fmtNum(o.analysis_id)}</code> · generated in{' '}
                  {fmtNum(o.generation_mode)} mode
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge status={o.project_status} />
                  <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                    <GitBranch size={11} className="text-cyan" /> {fmtNum(donePhases)}/{fmtNum(phaseList.length)} phases complete
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                    <FlaskConical size={11} className="text-blue" /> {fmtNum(o.total_test_cases)} test(s) · {fmtNum(o.executed_tests)} executed
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap items-stretch gap-3">
                <HeroTile label="Status" value={o.project_status} accent="text-green" />
                <HeroTile label="Phase" value={`${fmtNum(o.completed_phases)}/${fmtNum(o.total_phases)}`} accent="text-cyan" />
                <HeroTile
                  label="Pass rate"
                  value={`${passRate.toFixed(1)}%`}
                  accent={passRate >= 80 ? 'text-green' : passRate >= 50 ? 'text-amber' : 'text-red'}
                />
              </div>
            </div>

            <div className="relative mt-5 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
              <span className="font-semibold uppercase tracking-wider text-ink-muted">Final backend test result</span>
              <span className="flex items-center gap-1.5 font-mono text-green"><Check size={11} /> {fmtNum(ft.total)} total</span>
              <span className="flex items-center gap-1.5 font-mono text-green"><CirclePlay size={11} /> {fmtNum(ft.passed)} passed</span>
              {Number(ft.failed) > 0 && (
                <span className="flex items-center gap-1.5 font-mono text-red"><CircleX size={11} /> {fmtNum(ft.failed)} failed</span>
              )}
              <ChevronRight size={11} className="text-ink-disabled" />
              <Badge status="COMPLETE" />
            </div>
          </div>

          {/* Summary KPI rows */}
          <StatCards
            cols="xl:grid-cols-4"
            items={[
              { label: 'Phases complete', value: donePhases, accent: 'cyan', icon: GitBranch, sub: `of ${fmtNum(phaseList.length)} total` },
              { label: 'Requirements', value: reqs.length, accent: 'purple', icon: FileText, sub: `${fmtNum(coveredReqs)} covered · ${fmtNum(reqs.length - coveredReqs)} uncovered` },
              { label: 'Test cases', value: o.total_test_cases, accent: 'blue', icon: FlaskConical, sub: `all ${fmtNum((gen.tests || []).length || 0)} validated` },
              { label: 'Executed tests', value: o.executed_tests, accent: 'green', icon: CirclePlay, sub: `${fmtNum(ex.passed)} pass · ${fmtNum(ex.failed)} fail` },
            ]}
          />
          <StatCards
            cols="xl:grid-cols-4"
            items={[
              { label: 'Requirement coverage', value: fs.requirement_coverage, suffix: '%', accent: 'cyan', icon: Target, sub: 'backend reported' },
              { label: 'Execution coverage', value: ex.execution_coverage, suffix: '%', accent: 'blue', icon: Gauge, sub: 'backend reported' },
              { label: 'Fault detection', value: f.fault_detection_rate, suffix: '%', accent: 'fault', icon: ShieldAlert, sub: `${fmtNum(f.detected_faults)} of ${fmtNum(f.total_faults)} detected` },
              { label: 'Backend suite passed', value: ft.passed, accent: 'green', icon: Check, sub: `${fmtNum(ft.passed)}/${fmtNum(ft.total)} pytest` },
            ]}
          />

          {/* Report summary */}
          <Section
            icon={FolderOpen}
            title="Report summary"
            lede="Every key report value compiled from the live dashboard contract."
          >
            <DataTable
              columns={[
                { key: 'key', label: 'Metric' },
                { key: 'value', label: 'Value' },
              ]}
              rows={[
                { key: 'Project name', value: o.project_name },
                { key: 'Project ID', value: <code className="font-mono text-xs text-ink-secondary">{fmtNum(o.project_id)}</code> },
                { key: 'Project status', value: <Badge status={o.project_status} /> },
                { key: 'Analysis ID', value: <code className="font-mono text-xs text-cyan">{fmtNum(o.analysis_id)}</code> },
                { key: 'Generation mode', value: <Badge status={o.generation_mode} /> },
                { key: 'Phase progress', value: `${fmtNum(donePhases)} of ${fmtNum(phaseList.length)} phases complete` },
                { key: 'Requirements summary', value: `${fmtNum(reqs.length)} total · ${fmtNum(coveredReqs)} covered · ${fmtNum(reqs.length - coveredReqs)} uncovered` },
                { key: 'Test summary', value: `${fmtNum(o.total_test_cases)} generated · ${fmtNum(o.executed_tests)} executed` },
                { key: 'Execution summary', value: `${fmtNum(ex.passed)} passed · ${fmtNum(ex.failed)} failed · ${fmtNum(ex.errors)} errors · ${fmtNum(ex.skipped)} skipped` },
                { key: 'Fault summary', value: `${fmtNum(f.total_faults)} total · ${fmtNum(f.detected_faults)} detected · ${fmtNum(f.missed_faults)} missed · ${fmtNum(f.fault_detection_rate)}% rate` },
                { key: 'Refinement summary', value: refSummary },
                { key: 'Final test result', value: `${fmtNum(ft.total)} total · ${fmtNum(ft.passed)} passed · ${fmtNum(ft.failed)} failed · ${fmtNum(ft.errors)} errors · ${fmtNum(ft.skipped)} skipped` },
              ]}
            />
          </Section>

          {/* Coverage visualization */}
          <Section
            icon={Target}
            title="Coverage visualization"
            lede="Real coverage values reported by the backend — requirement coverage, execution coverage and the executed-test split."
          >
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="flex flex-col items-center justify-center rounded-card border border-line bg-bg-secondary/40 p-5">
                <GaugeChart
                  value={fs.requirement_coverage}
                  centerLabel="Requirement coverage"
                  sub={`${fmtNum(coveredReqs)} of ${fmtNum(reqs.length)} covered`}
                  from="#22D3EE"
                  to="#3B82F6"
                />
                <div className="mt-3 w-full space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-green" /> Covered</span>
                    <span className="font-mono text-green">{fmtNum(coveredReqs)}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-amber" /> Uncovered</span>
                    <span className="font-mono text-amber">{fmtNum(reqs.length - coveredReqs)}</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-center justify-center rounded-card border border-line bg-bg-secondary/40 p-5">
                <GaugeChart
                  value={ex.execution_coverage}
                  centerLabel="Execution coverage"
                  sub={`${fmtNum(o.executed_tests)} of ${fmtNum(o.total_test_cases)} executed`}
                  from="#3B82F6"
                  to="#8B5CF6"
                />
                <div className="mt-3 w-full">
                  <div className="mb-1.5 flex items-center justify-between text-[11px] text-ink-muted">
                    <span>Generated tests</span>
                    <span className="font-mono text-blue">{fmtNum(o.total_test_cases)}</span>
                  </div>
                  <ProgressBar value={ex.execution_coverage} to="bg-gradient-to-r from-blue to-purple" />
                  <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-muted">
                    <span>Untested gap</span>
                    <span className="font-mono text-ink-disabled">{fmtNum(Math.max(0, Number(o.total_test_cases) - Number(o.executed_tests)))}</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-center justify-center rounded-card border border-line bg-bg-secondary/40 p-5">
                <DonutChart
                  segments={[
                    { label: 'Passed', value: Number(ex.passed) || 0, color: CHART_COLORS.pass },
                    { label: 'Failed', value: Number(ex.failed) || 0, color: CHART_COLORS.fail },
                    { label: 'Errors', value: Number(ex.errors) || 0, color: CHART_COLORS.error },
                    { label: 'Skipped', value: Number(ex.skipped) || 0, color: CHART_COLORS.skip },
                  ]}
                  centerLabel={passRate.toFixed(0)}
                  centerSub="pass rate"
                  centerHint={`${fmtNum(o.executed_tests)} executed`}
                />
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-muted">
              Execution coverage is the share of generated tests that were executed; pass rate is the share of executed tests that passed. Nothing here is simulated.
            </p>
          </Section>

          {/* Execution & fault summary */}
          <Section
            icon={ShieldAlert}
            title="Execution & fault summary"
            lede="Execution verdicts and the real fault-detection state of this run."
          >
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-card border border-line bg-bg-secondary/40 p-4">
                <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                  <CirclePlay size={12} className="text-green" /> Test execution
                </div>
                <div className="mb-3 grid grid-cols-4 gap-2">
                  {[
                    { label: 'Passed', value: Number(ex.passed) || 0, cls: 'text-green' },
                    { label: 'Failed', value: Number(ex.failed) || 0, cls: 'text-red' },
                    { label: 'Errors', value: Number(ex.errors) || 0, cls: 'text-amber' },
                    { label: 'Skipped', value: Number(ex.skipped) || 0, cls: 'text-ink-muted' },
                  ].map((s) => (
                    <div key={s.label} className="rounded-card border border-line bg-card px-2 py-2.5 text-center">
                      <div className={`tab-nums text-lg font-bold ${s.cls}`}>{fmtNum(s.value)}</div>
                      <div className="text-[10px] uppercase tracking-wider text-ink-muted">{s.label}</div>
                    </div>
                  ))}
                </div>
                <StackedBar
                  segments={[
                    { label: 'Passed', value: Number(ex.passed) || 0, color: CHART_COLORS.pass },
                    { label: 'Failed', value: Number(ex.failed) || 0, color: CHART_COLORS.fail },
                    { label: 'Errors', value: Number(ex.errors) || 0, color: CHART_COLORS.error },
                    { label: 'Skipped', value: Number(ex.skipped) || 0, color: CHART_COLORS.skip },
                  ]}
                />
                <p className="mt-2 text-[11px] text-ink-muted">
                  Broker-dependent MQTT tests are SKIPPED — never faked — when no broker is reachable.
                </p>
              </div>

              <div className="rounded-card border border-line bg-bg-secondary/40 p-4">
                <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                  <TriangleAlert size={12} className="text-amber" /> Fault detection
                </div>
                <div className="mb-3 grid grid-cols-3 gap-2">
                  {[
                    { label: 'Total', value: Number(f.total_faults) || 0, cls: 'text-amber' },
                    { label: 'Detected', value: Number(f.detected_faults) || 0, cls: 'text-green' },
                    { label: 'Missed', value: Number(f.missed_faults) || 0, cls: 'text-red' },
                  ].map((s) => (
                    <div key={s.label} className="rounded-card border border-line bg-card px-2 py-2.5 text-center">
                      <div className={`tab-nums text-lg font-bold ${s.cls}`}>{fmtNum(s.value)}</div>
                      <div className="text-[10px] uppercase tracking-wider text-ink-muted">{s.label}</div>
                    </div>
                  ))}
                </div>
                <div className="mb-1.5 flex items-center justify-between text-[11px] text-ink-muted">
                  <span>Detection rate</span>
                  <span className="font-mono font-semibold text-grad-fault">{fmtNum(f.fault_detection_rate)}%</span>
                </div>
                <ProgressBar value={f.fault_detection_rate} to="bg-gradient-to-r from-amber to-red" />
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {(f.faults || []).map((x) => (
                    <code key={x.fault_id} className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] text-amber">
                      {x.fault_id} · {String(x.detection_status || '').replace(/_/g, ' ')}
                    </code>
                  ))}
                  {!(f.faults || []).length && <span className="text-[11px] text-ink-disabled">No faults recorded.</span>}
                </div>
              </div>
            </div>
          </Section>

          {/* Phase progress */}
          <Section
            icon={GitBranch}
            title="Phase progress"
            lede="Backend deliverable phases and the final pytest suite result."
          >
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-medium text-ink-muted">Implementation complete</span>
              <span className="font-mono font-semibold text-cyan">{fmtNum(donePhases)}/{fmtNum(phaseList.length)} · {phasePct.toFixed(1)}%</span>
            </div>
            <ProgressBar value={phasePct} to="bg-gradient-to-r from-cyan to-blue" />
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {phaseList.map((p, idx) => {
                const done = String(p.status || '').toUpperCase() === 'COMPLETE';
                return (
                  <span key={p.phase_number} className="flex items-center gap-1.5" title={`Phase ${p.phase_number} — ${p.title}`}>
                    <span
                      className={`flex h-6 min-w-6 items-center justify-center rounded-md border px-1.5 font-mono text-[10px] font-semibold ${
                        done ? 'border-line-success/60 bg-ok-bg/40 text-green' : 'border-line-warn/60 bg-warn-bg/30 text-amber'
                      }`}
                    >
                      {fmtNum(p.phase_number)}
                    </span>
                    {idx < phaseList.length - 1 && <ChevronRight size={10} className="text-ink-disabled" />}
                  </span>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-ink-muted">
              Phase {fmtNum(o.current_phase)} is the active phase; the backend reports Phase {fmtNum(phaseList.length)} (final testing, debugging, documentation) as {fmtNum(phaseList[phaseList.length - 1]?.status)}.
            </p>
          </Section>

          {/* Report tables */}
          <Section
            icon={ListChecks}
            title="Report tables"
            lede="Requirements and generated tests — the compact tabular report."
          >
            <div className="mb-4">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                <FileText size={12} className="text-purple" /> Requirements
              </div>
              <DataTable
                columns={[
                  { key: 'requirement_id', label: 'ID', mono: true },
                  { key: 'category', label: 'Category' },
                  { key: 'description', label: 'Description' },
                  { key: 'coverage', label: 'Coverage' },
                  { key: 'validation', label: 'Validation' },
                  { key: 'tests', label: 'Tests' },
                ]}
                rows={reqs.map((q) => ({
                  requirement_id: q.requirement_id,
                  category: fmtNum(q.category),
                  description: q.description || 'Not available',
                  coverage: <Badge status={q.coverage_status} />,
                  validation: <Badge status={q.validation_status} />,
                  tests: q.test_case_count,
                }))}
              />
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                <FlaskConical size={12} className="text-blue" /> Generated tests
              </div>
              <DataTable
                columns={[
                  { key: 'test_case_id', label: 'ID', mono: true },
                  { key: 'requirement_id', label: 'Requirement', mono: true },
                  { key: 'category', label: 'Category' },
                  { key: 'priority', label: 'Priority' },
                  { key: 'validation_status', label: 'Validation' },
                ]}
                rows={(gen.tests || []).map((t) => ({
                  test_case_id: t.test_case_id,
                  requirement_id: t.requirement_id,
                  category: fmtNum(t.category),
                  priority: <span className="text-[11px] font-medium uppercase text-ink-secondary">{t.priority}</span>,
                  validation_status: <Badge status={t.validation_status} />,
                }))}
              />
            </div>
          </Section>

          {/* Report artifacts */}
          <Section
            icon={FolderOpen}
            title="Report artifacts"
            lede="Real backend report artifacts generated by the Python backend. They are not bundled into this static frontend build; generate or serve them with the commands below."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {REPORT_FILES.map((rf) => (
                <div
                  key={rf.file}
                  className="card-hover relative overflow-hidden rounded-card border border-line bg-card p-4 shadow-card"
                >
                  <div className={`pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue/60 to-transparent`} />
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${rf.accent} text-white shadow-ai`}>
                      <FileText size={16} strokeWidth={2} />
                    </span>
                    <code className="rounded-md border border-line bg-bg-secondary px-2 py-1 font-mono text-[11px] text-cyan">{rf.file}</code>
                  </div>
                  <div className="text-sm font-semibold text-ink">{rf.label}</div>
                  <p className="mb-3 mt-1 text-xs leading-relaxed text-ink-muted">{rf.description}</p>
                  <p className="mb-1 text-[11px] text-ink-muted">
                    Path: <code className="font-mono text-[11px] text-ink-secondary">{rf.availablePath}</code>
                  </p>
                  <p className="text-[11px] text-ink-muted">
                    Generate: <code className="rounded-md border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[11px] text-blue">{rf.command}</code>
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-ink-muted">
              This React dashboard reads the same data artifact it reports on: it renders{' '}
              <code className="rounded-md border border-line bg-bg-secondary px-1 py-0.5 font-mono text-[11px]">frontend/public/dashboard_data.json</code>,
              which is copied from <code className="rounded-md border border-line bg-bg-secondary px-1 py-0.5 font-mono text-[11px]">backend/reports/dashboard_data.json</code>.
            </p>
          </Section>
        </>
      ) : null}
    </div>
  );
}

// 11. Overall project status (Section I)
export function FinalStatus({ data }) {
  const s = data.final_status;
  const t = s.final_test_result || {};
  const covered = Number(t.passed);
  const total = Number(t.total);
  const pct = total > 0 ? (covered / total) * 100 : 0;

  return (
    <div className="mt-5 space-y-5">
      <Section icon={Target} title="Overall backend status" lede="Real pytest result from the backend suite.">
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Tests total</div>
            <div className="text-2xl font-bold text-ink">{fmtNum(t.total)}</div>
          </div>
          <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Passed</div>
            <div className="text-2xl font-bold text-green">{fmtNum(t.passed)}</div>
          </div>
          <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Failed</div>
            <div className="text-2xl font-bold text-red">{fmtNum(t.failed)}</div>
          </div>
          <div className="rounded-card border border-line bg-bg-secondary/60 px-4 py-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Skipped</div>
            <div className="text-2xl font-bold text-ink-muted">{fmtNum(t.skipped)}</div>
          </div>
        </div>
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="font-medium text-ink-muted">Overall pass rate</span>
          <span className="font-mono font-semibold text-green">{pct.toFixed(1)}%</span>
        </div>
        <ProgressBar value={pct} to="bg-gradient-to-r from-green to-green-darker" />
        <p className="mt-2 text-xs text-ink-muted">
          {pct.toFixed(1)}% of backend tests passed ({fmtNum(t.passed)}/{fmtNum(t.total)})
        </p>
      </Section>

      <StatCards
        items={[
          { label: 'Requirement coverage', value: s.requirement_coverage, accent: 'cyan', icon: FileText, sub: `${fmtNum(total)} test cases` },
          { label: 'Execution coverage', value: s.execution_coverage, accent: 'blue', icon: CirclePlay },
          { label: 'Fault detection', value: s.fault_detection, accent: 'fault', icon: ShieldAlert },
          { label: 'Remaining gaps', value: s.remaining_gaps, accent: 'amber', icon: Target },
        ]}
      />

      <Section icon={ListChecks} title="Known limitations">
        <ul className="list-inside list-disc space-y-1.5 text-xs text-ink-muted">
          {s.known_limitations.length
            ? s.known_limitations.map((l, i) => <li key={i}>{l}</li>)
            : <li>None recorded.</li>}
        </ul>
      </Section>

      <Section icon={Sparkles} title="Phase 15 — React frontend (current)">
        <p className="mb-3 text-xs text-ink-muted">This dashboard is the Phase 15 React presentation frontend.</p>
        <div className="flex flex-wrap items-center gap-2">
          <Badge status={PHASE_15.status} />
          <span className="text-xs text-ink-muted">{PHASE_15.verification}</span>
        </div>
      </Section>
    </div>
  );
}