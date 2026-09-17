// Phase 15 — React frontend connected to the real Python backend API.
// Industrial "AI + IoT Test Automation Control Center" shell with the
// EXACT VISUAL DESIGN SYSTEM (dark control-center theme).

import { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  Brain,
  ClipboardCheck,
  CirclePlay,
  FileBarChart,
  GitBranch,
  LayoutDashboard,
  RefreshCw,
  Server,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import { fetchDashboard, fetchHealth, API_BASE_URL } from './api.js';
import { Badge, StatusDot, Skeleton } from './components/ui.jsx';

import {
  Overview,
  Phases,
  Requirements,
  Knowledge,
  Generation,
  Execution,
  Faults,
  Refinement,
  Traceability,
  Reports,
  FinalStatus,
} from './components/Sections.jsx';

// Grouped navigation: visual hierarchy for the control-center sidebar.
const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [{ key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    label: 'Pipeline',
    items: [
      { key: 'phases', label: 'Phase Status', icon: Activity },
      { key: 'requirements', label: 'Requirements', icon: ClipboardCheck },
      { key: 'knowledge', label: 'RAG / Knowledge', icon: Brain },
      { key: 'generation', label: 'Test Generation', icon: Sparkles },
      { key: 'execution', label: 'Execution', icon: CirclePlay },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { key: 'faults', label: 'Fault Analysis', icon: ShieldAlert },
      { key: 'refinement', label: 'Refinement', icon: RefreshCw },
      { key: 'traceability', label: 'Traceability', icon: GitBranch },
      { key: 'reports', label: 'Reports', icon: FileBarChart },
    ],
  },
];

const NAV = NAV_GROUPS.flatMap((group) => group.items);
const TITLES = Object.fromEntries(NAV.map((item) => [item.key, item.label]));

function fmtProjectName(data) {
  return (
    data?.overview?.project_name ||
    'Autonomous RAG-Based IoT Test Generation & Fault Detection Framework'
  );
}

function fmtNum(value) {
  if (value === null || value === undefined || value === '' || value === 'Not available') {
    return '—';
  }
  return String(value);
}

function SidebarLink({ item, active, onClick }) {
  const isActive = active === item.key;
  return (
    <button
      onClick={onClick}
      aria-current={isActive ? 'page' : undefined}
      title={item.label}
      className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition-all duration-200 ${
        isActive
          ? 'bg-gradient-to-r from-cyan/10 via-blue/10 to-transparent text-ink shadow-[0_0_18px_rgba(34,211,238,0.08)]'
          : 'text-ink-muted hover:translate-x-0.5 hover:bg-card-elevated/50 hover:text-ink'
      }`}
    >
      {isActive && (
        <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-gradient-to-b from-cyan to-blue shadow-[0_0_12px_rgba(34,211,238,0.5)]" />
      )}
      <item.icon
        size={16}
        strokeWidth={2}
        className={`shrink-0 transition-all duration-200 ${
          isActive ? 'text-cyan' : 'text-ink-disabled group-hover:scale-105 group-hover:text-ink-muted'
        }`}
      />
      {item.label}
    </button>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-5" aria-hidden>
      <div className="rounded-panel border border-line bg-header p-6">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="mt-3 h-7 w-2/3" />
        <div className="mt-4 flex gap-2">
          <Skeleton className="h-5 w-24 rounded-pill" />
          <Skeleton className="h-5 w-24 rounded-pill" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <div key={i} className="rounded-card border border-line bg-card p-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-3 h-8 w-16" />
          </div>
        ))}
      </div>
      <Skeleton className="h-32 w-full rounded-panel" />
    </div>
  );
}

function AppShell({ data, health, loading, error, active, setActive, refresh }) {
  const overview = data?.overview || {};
  const execution = data?.execution || {};
  const finalStatus = data?.final_status || {};

  const passed = execution?.passed ?? finalStatus?.final_test_result?.passed ?? 0;
  const failed = execution?.failed ?? finalStatus?.final_test_result?.failed ?? 0;

  // REAL backend status, driven exclusively by GET /api/health.
  const healthOk = health?.status === 'ok';
  const backend = !health && loading
    ? { tone: 'warn', label: 'Connecting', pulse: false }
    : healthOk
      ? { tone: 'ok', label: 'Online', pulse: true }
      : { tone: 'bad', label: 'Offline', pulse: false };

  const statusPill =
    backend.tone === 'ok'
      ? 'border-line-success/60 bg-ok-bg text-green'
      : backend.tone === 'bad'
        ? 'border-line-error/60 bg-err-bg text-red'
        : 'border-line-warn/60 bg-warn-bg text-amber';

  const mode = overview.generation_mode || health?.generation_mode || null;
  const curPhase = health?.current_phase != null ? health.current_phase : overview.current_phase != null ? overview.current_phase : null;
  const totalPhase = health?.total_phases != null ? health.total_phases : overview.total_phases != null ? overview.total_phases : null;
  const analysisId = overview.analysis_id || health?.analysis_id || null;
  const ActiveIcon = NAV.find((n) => n.key === active)?.icon || LayoutDashboard;

  return (
    <div className="flex min-h-screen bg-bg-main text-ink">

      {/* Sidebar */}
      <aside className="sticky top-0 z-30 flex h-screen w-64 flex-shrink-0 flex-col border-r border-line/60 bg-sidebar text-ink-secondary max-lg:hidden">
        {/* Branding */}
        <div className="relative px-4 pb-4 pt-5">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan/50 to-transparent" />
          <div className="flex items-center gap-3">
            <span className="relative flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-blue text-bg-main shadow-ai">
              <Bot size={19} strokeWidth={2.2} />
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-sidebar bg-green" />
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-black leading-tight tracking-wide text-white">
                AI TEST AUTOMATION
              </div>
              <div className="mt-0.5 truncate text-[10px] text-ink-muted">
                AI · RAG · IoT Control Center
              </div>
            </div>
          </div>
        </div>

        {/* Primary navigation */}
        <nav className="flex-1 overflow-y-auto px-3 pb-4" aria-label="Primary sections">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="mt-4 px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-ink-disabled">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <SidebarLink key={item.key} item={item} active={active} onClick={() => setActive(item.key)} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* System status */}
        <div className="border-t border-line/60 p-3">
          <div className="relative overflow-hidden rounded-card border border-line bg-bg-secondary/60 px-3 py-2.5">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan/40 to-transparent" />
            <div className="flex items-center justify-between gap-2">
              <span
                className={`flex items-center gap-2 text-xs font-semibold ${
                  backend.tone === 'ok' ? 'text-green' : backend.tone === 'bad' ? 'text-red' : 'text-amber'
                }`}
              >
                <StatusDot tone={backend.tone} pulse={backend.pulse} size="h-2 w-2" />
                Backend {backend.label}
              </span>
              {health?.api_version != null && (
                <span className="font-mono text-[10px] text-ink-disabled">v{health.api_version}</span>
              )}
            </div>
            {(mode || curPhase != null) && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {mode ? (
                  <span className="inline-flex items-center gap-1 rounded-pill border border-line/80 bg-card px-2 py-0.5 font-mono text-[10px] text-cyan">
                    {mode} mode
                  </span>
                ) : null}
                {curPhase != null ? (
                  <span className="inline-flex items-center gap-1 rounded-pill border border-line/80 bg-card px-2 py-0.5 font-mono text-[10px] text-ink-muted">
                    Phase {curPhase}{totalPhase != null ? `/${totalPhase}` : ''}
                  </span>
                ) : null}
              </div>
            )}
            <div className="mt-2 flex items-center gap-1.5 text-[10px] text-ink-muted">
              <Server size={10} className={backend.tone === 'ok' ? 'text-green' : 'text-red'} />
              <code className="truncate font-mono text-[10px] text-ink-disabled">{API_BASE_URL}</code>
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">

        {/* Header */}
        <header className="sticky top-0 z-20 border-b border-line/60 bg-header/95 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-6 py-3 max-lg:px-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-blue text-bg-main shadow-ai">
                <ActiveIcon size={16} strokeWidth={2.2} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-[15px] font-bold text-ink">{TITLES[active]}</div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-muted">
                  <span className="truncate">{loading ? 'Connecting to backend…' : fmtProjectName(data)}</span>
                  {analysisId ? (
                    <span className="hidden font-mono text-[10px] text-ink-disabled sm:inline">
                      · {String(analysisId).slice(0, 8)}
                    </span>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex flex-shrink-0 items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-[11px] font-semibold ${statusPill}`}>
                <StatusDot tone={backend.tone} pulse={backend.pulse} size="h-1.5 w-1.5" />
                Backend {backend.label}
              </span>

              {mode ? <Badge status={mode} /> : null}

              {curPhase != null && totalPhase != null ? (
                <span className="hidden items-center gap-1.5 rounded-pill border border-line/80 bg-bg-secondary px-2.5 py-1 text-[11px] font-semibold text-ink-muted md:inline-flex">
                  <Activity size={12} className="text-blue" />
                  Phase {curPhase}/{totalPhase}
                </span>
              ) : null}

              <span className="hidden rounded-pill border border-line-success/60 bg-ok-bg px-2.5 py-1 text-[11px] font-semibold text-green xl:inline">
                {fmtNum(passed)} Passed
              </span>
              {Number(failed) > 0 && (
                <span className="hidden rounded-pill border border-line-error/60 bg-err-bg px-2.5 py-1 text-[11px] font-semibold text-red xl:inline">
                  {fmtNum(failed)} Failed
                </span>
              )}

              <button
                onClick={refresh}
                disabled={loading}
                className="btn-ui flex items-center gap-1.5 rounded-lg border border-line bg-bg-secondary px-3 py-1.5 text-xs font-medium text-ink-secondary hover:border-line-active/60 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw size={13} strokeWidth={2.2} className={loading ? 'animate-spin' : ''} />
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>
        </header>

        {/* Mobile navigation */}
        <nav
          className="flex gap-2 overflow-x-auto border-b border-line/60 bg-header/60 px-4 py-2.5 lg:hidden"
          aria-label="Sections (mobile)"
        >
          {NAV.map((item) => (
            <button
              key={item.key}
              onClick={() => setActive(item.key)}
              aria-current={active === item.key ? 'page' : undefined}
              title={item.label}
              className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
                active === item.key
                  ? 'border-line-active/40 bg-gradient-to-r from-cyan/15 to-blue/15 text-cyan'
                  : 'border-transparent text-ink-muted hover:bg-bg-secondary hover:text-ink'
              }`}
            >
              <item.icon size={14} strokeWidth={2} />
              {item.label}
            </button>
          ))}
        </nav>

        {/* API status strip */}
        {data && !error && (
          <div className="mx-6 mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-card border border-line bg-card px-4 py-2 text-xs text-ink-muted max-lg:mx-4">
            <StatusDot tone="ok" />
            <span>
              Connected to Python backend: <code className="font-mono text-cyan">{API_BASE_URL}</code>
            </span>
            <span className="hidden sm:inline">· GET /api/dashboard</span>
            {analysisId ? (
              <span className="hidden font-mono text-[10px] text-ink-disabled md:inline">· {analysisId}</span>
            ) : null}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mx-6 mt-4 rounded-card border border-line-error/60 bg-err-bg p-4 text-red max-lg:mx-4">
            <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
              <ShieldAlert size={15} strokeWidth={2} />
              Backend API connection failed
            </h3>
            <p className="text-xs text-red/80">{error}</p>
            <p className="mt-2 text-xs text-red/80">Make sure the backend is running:</p>
            <code className="mt-1 block rounded-lg border border-line-error/40 bg-black/20 px-3 py-2 font-mono text-xs text-red/90">
              python -m app.dashboard --port 8877
            </code>
            <button
              onClick={refresh}
              className="btn-ui mt-3 rounded-lg bg-gradient-to-r from-red to-amber px-3.5 py-1.5 text-xs font-semibold text-white"
            >
              Try Again
            </button>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !data && (
          <main className="flex-1 px-6 py-6 max-lg:px-4">
            <DashboardSkeleton />
          </main>
        )}

        {/* Main content */}
        {!loading && data && (
          <main key={active} className="anim-entry flex-1 px-6 pb-12 pt-6 max-lg:px-4">
            <div className="mx-auto w-full max-w-7xl">
              {active === 'dashboard' && (
                <>
                  <Overview data={data} />
                  <FinalStatus data={data} />
                </>
              )}
              {active === 'phases' && <Phases data={data} />}
              {active === 'requirements' && <Requirements data={data} />}
              {active === 'knowledge' && <Knowledge data={data} />}
              {active === 'generation' && <Generation data={data} />}
              {active === 'execution' && <Execution data={data} />}
              {active === 'faults' && <Faults data={data} />}
              {active === 'refinement' && <Refinement data={data} />}
              {active === 'traceability' && <Traceability data={data} />}
              {active === 'reports' && <Reports data={data} />}
            </div>
          </main>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [active, setActive] = useState('dashboard');

  async function loadBackendData() {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, healthData] = await Promise.all([fetchDashboard(), fetchHealth()]);
      setData(dashboardData);
      setHealth(healthData);
    } catch (err) {
      console.error('Backend API error:', err);
      setError(err?.message || 'Unable to connect to the Python backend.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBackendData();
  }, []);

  return (
    <AppShell
      data={data}
      health={health}
      loading={loading}
      error={error}
      active={active}
      setActive={setActive}
      refresh={loadBackendData}
    />
  );
}