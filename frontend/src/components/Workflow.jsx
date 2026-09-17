// Phase 15 — AI / RAG + Test Automation workflow visual.
// States are DERIVED from REAL backend data (never invented):
//   Requirement → RAG Retrieval → Knowledge → AI Test Generation →
//   Execution → Fault Detection → Autonomous Refinement → Traceability.
// Numbered stages with status chips, real-data metric sublines, and an
// animated connector that draws in once (left-to-right on wide screens).
// All animation classes come from index.css (.workflow-line, .anim-entry,
// .card-hover) and honour prefers-reduced-motion.

import { Check, CircleDashed, TriangleAlert } from 'lucide-react';
import {
  BookOpen,
  CirclePlay,
  Database,
  FileText,
  GitBranch,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react';
import { isNA } from '../data.js';

const NODE_META = [
  { key: 'requirement', label: 'Requirement', Icon: FileText, grad: 'grad-primary', text: 'text-cyan' },
  { key: 'rag', label: 'RAG Retrieval', Icon: Search, grad: 'grad-ai', text: 'text-blue' },
  { key: 'knowledge', label: 'Knowledge', Icon: Database, grad: 'grad-ai', text: 'text-purple' },
  { key: 'generation', label: 'AI Test Generation', Icon: Sparkles, grad: 'grad-ai', text: 'text-blue' },
  { key: 'execution', label: 'Test Execution', Icon: CirclePlay, grad: 'grad-primary', text: 'text-cyan' },
  { key: 'fault', label: 'Fault Detection', Icon: TriangleAlert, grad: 'grad-fault', text: 'text-amber' },
  { key: 'refinement', label: 'Autonomous Refinement', Icon: RefreshCw, grad: 'grad-ai', text: 'text-cyan' },
  { key: 'traceability', label: 'Traceability', Icon: GitBranch, grad: 'grad-success', text: 'text-green' },
];

/* Derive stage state + a concise real-data metric line for each stage. */
function deriveStates(data) {
  const o = data?.overview || {};
  const k = data?.knowledge || {};
  const g = data?.generation || {};
  const e = data?.execution || {};
  const f = data?.fault_summary || {};
  const r = data?.refinement || {};
  const tr = data?.traceability?.rows || [];

  const reqs = data?.requirements || [];
  const metric = (state, note, value) => ({ state, note, value });

  return {
    requirement: metric(
      reqs.length > 0 ? 'done' : 'idle',
      reqs.length > 0 ? 'Complete' : 'Pending',
      reqs.length > 0 ? `${reqs.length} requirement${reqs.length === 1 ? '' : 's'}` : 'Not available'
    ),
    rag: metric(
      (k.retrieved_topics || []).length > 0 ? 'done' : 'idle',
      (k.retrieved_topics || []).length > 0 ? 'Complete' : 'Pending',
      (k.retrieved_topics || []).length > 0 ? `${k.retrieved_topics.length} topics` : 'Not available'
    ),
    knowledge: metric(
      Number(k.document_count) > 0 ? 'done' : 'idle',
      Number(k.document_count) > 0 ? 'Complete' : 'Pending',
      Number(k.document_count) > 0 ? `${k.document_count} documents` : 'Not available'
    ),
    generation: metric(
      Number(g.total_generated) > 0 ? 'done' : 'idle',
      Number(g.total_generated) > 0 ? 'Complete' : 'Pending',
      Number(g.total_generated) > 0 ? `${g.total_generated} cases generated` : 'Not available'
    ),
    execution: metric(
      Number(e.total_executed) > 0 ? 'done' : 'idle',
      Number(e.total_executed) > 0 ? 'Complete' : 'Pending',
      Number(e.total_executed) > 0
        ? `${e.total_executed} executed · ${Number(e.passed) || 0} passed`
        : 'Not available'
    ),
    fault: {
      state: 'fault',
      note:
        Number(f.total_faults) > 0
          ? `${String(f.detected_faults ?? 0)} detected / ${String(f.missed_faults ?? 0)} missed`
          : 'No faults injected',
      value: !isNA(f.total_faults) ? `${f.total_faults} faults injected` : 'Not available',
      alert: Number(f.missed_faults) > 0,
    },
    refinement: metric(
      Boolean(r.available) ? 'done' : 'idle',
      r.available ? `Complete · ${String(r.stop_reason || '').toUpperCase()}` : 'Pending',
      r.available
        ? `coverage ${isNA(r.coverage_before) ? '—' : Number(r.coverage_before).toFixed(0)}% → ${isNA(r.coverage_after) ? '—' : Number(r.coverage_after).toFixed(0)}%`
        : 'Not available'
    ),
    traceability: metric(
      tr.length > 0 ? 'done' : 'idle',
      tr.length > 0 ? 'Complete' : 'Pending',
      tr.length > 0 ? `${tr.length} requirement trace(s)` : 'Not available'
    ),
  };
}

/* Connector tone driven by its SOURCE stage (green = completed, amber =
   degraded/fault path, neutral = not yet reached). */
function lineClass(node) {
  if (node.state === 'done') {
    return 'bg-gradient-to-b from-green/60 to-transparent xl:bg-gradient-to-r';
  }
  if (node.key === 'fault') {
    return 'bg-gradient-to-b from-amber/50 to-transparent xl:bg-gradient-to-r';
  }
  return 'bg-gradient-to-b from-line to-transparent xl:bg-gradient-to-r';
}

export default function AiWorkflow({ data }) {
  const states = deriveStates(data);
  const overall = (data?.overview || {}).current_phase;
  const firstIdle = NODE_META.findIndex((n) => n.key !== 'fault' && states[n.key].state !== 'done');

  return (
    <div>
      {/* Pipeline header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-ink-muted">
          <span className="h-1.5 w-1.5 rounded-pill bg-gradient-to-r from-cyan to-blue" />
          Autonomous RAG pipeline
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-pill border border-line/70 bg-bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
          {NODE_META.length} stages
          {!isNA(overall) && <span className="text-ink-disabled">· framework phase {overall}</span>}
        </span>
      </div>

      <ol className="grid gap-y-4 sm:grid-cols-2 sm:gap-x-4 xl:grid-cols-4 xl:gap-x-6 xl:gap-y-8">
        {NODE_META.map((node, i) => {
          const st = states[node.key];
          const isDone = st.state === 'done';
          const isNext = i === firstIdle;
          const isFaultNode = node.key === 'fault';
          const pillTone = isFaultNode
            ? st.alert
              ? 'border-line-error/60 bg-err-bg text-red'
              : 'border-line-warn/60 bg-warn-bg text-amber'
            : isDone
              ? 'border-line-success/60 bg-ok-bg text-green'
              : 'border-line bg-bg-secondary text-ink-disabled';
          const pillIcon = isFaultNode ? TriangleAlert : isDone ? Check : CircleDashed;

          return (
            <li key={node.key} className="anim-entry relative" style={{ animationDelay: `${i * 70}ms` }}>
              {/* Connecting line — draws in once, subtle sheen sweeps left→right */}
              {i < NODE_META.length - 1 && (
                <span
                  aria-hidden
                  className={`workflow-line absolute left-[26px] top-[54px] hidden h-5 w-px sm:block xl:left-auto xl:right-[-22px] xl:top-[30px] xl:h-px xl:w-7 ${lineClass(st)}`}
                  style={{ animationDelay: `${320 + i * 130}ms` }}
                />
              )}

              {/* Stage card */}
              <div
                className={`card-hover group relative flex flex-col overflow-hidden rounded-card border bg-card p-4 transition-colors duration-200 ${
                  isNext ? 'border-line-active/50' : isDone ? 'border-line/80' : 'border-line/70'
                } ${isNext ? 'shadow-[0_0_22px_rgba(34,211,238,0.10)]' : ''}`}
                title={`${node.label} — ${st.note}`}
              >
                <div className="flex items-start gap-3">
                  {/* Numbered icon chip */}
                  <span
                    className={`relative flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg text-white shadow-ai ${node.grad}`}
                  >
                    <node.Icon size={20} strokeWidth={2} />
                    {isDone && (
                      <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-line-success/60 bg-ok-bg text-green">
                        <Check size={11} strokeWidth={3} />
                      </span>
                    )}
                  </span>

                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${node.text}`}>
                      <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded bg-bg-secondary font-mono text-[9px] font-semibold text-ink-disabled">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="truncate" title={node.label}>{node.label}</span>
                    </div>

<span className={`mt-1.5 inline-flex items-center gap-1.5 rounded-pill border px-2 py-0.5 text-[10px] font-semibold ${pillTone}`}>
  <pillIcon size={10} strokeWidth={2.4} />
  {st.note}
</span>

                    <div className="mt-2 truncate font-mono text-[10px] text-ink-muted" title={st.value}>
                      {st.value}
                    </div>
                  </div>
                </div>

                {isNext && (
                  <div className="mt-2.5 text-[10px] font-semibold uppercase tracking-wider text-cyan">Next in pipeline</div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-5 text-center text-[11px] text-ink-muted">
        Derives states from real DashboardData — no fabricated metrics.
      </p>
    </div>
  );
}