"""
Phase 12 — dashboard renderer (stdlib only).

WHY:
    The dashboard must run on Windows with no extra dependencies and no browser
    required for unit tests. This module renders the already-built
    `DashboardData` in two forms:
      - `render_html(...)`  -> a single self-contained HTML page (inline CSS,
                               no external assets) suitable for `http.server`.
      - `render_text(...)`  -> a plain-text view used by the console demo and
                               by headless tests (no browser needed).

    Rendering is a pure function of `DashboardData`; it never touches data.
"""

from __future__ import annotations

from html import escape

from app.dashboard import models as vm


# ------------------------------------------------------------------ HTML


def render_html(data: vm.DashboardData) -> str:
    ov = data.overview
    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    html.append(f"<title>{escape(ov.project_name)} — Dashboard</title>")
    html.append("<style>")
    html.append("body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1a1a1a;background:#f6f8fa}")
    html.append("h1{font-size:22px}h2{font-size:18px;margin-top:28px;border-bottom:2px solid #d0d7de;padding-bottom:4px}")
    html.append("table{border-collapse:collapse;width:100%;margin:8px 0 18px;background:#fff}")
    html.append("th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;font-size:13px}")
    html.append("th{background:#eef1f4}")
    html.append(".kv{display:grid;grid-template-columns:240px 1fr;gap:6px 18px;max-width:820px}")
    html.append(".kv span{font-weight:600}")
    html.append(".badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}")
    html.append(".ok{background:#dafbe1;color:#116329}.warn{background:#fff8c5;color:#7d4e00}")
    html.append(".bad{background:#ffebe9;color:#cf222e}.na{color:#6e7781}")
    html.append("</style></head><body>")
    html.append(f"<h1>{escape(ov.project_name)}</h1>")
    html.append(f"<p>Project ID: <code>{escape(ov.project_id)}</code> · "
                f"Analysis ID: <code>{escape(ov.analysis_id)}</code></p>")

    _h_htm(html, "A. Project Overview", _kv_html([
        ("Status", ov.project_status),
        ("Current phase", str(ov.current_phase) if ov.current_phase else vm.not_available()),
        ("Completed phases", f"{ov.completed_phases} / {ov.total_phases}"),
        ("Total requirements", _num(ov.total_requirements)),
        ("Total test cases", _num(ov.total_test_cases)),
        ("Executed tests", _num(ov.executed_tests)),
        ("Passed", _num(ov.passed)),
        ("Failed", _num(ov.failed)),
        ("Errors", _num(ov.errors)),
        ("Skipped", _num(ov.skipped)),
        ("Generation mode", f"<span class='badge {'ok' if ov.generation_mode=='MOCK' else 'warn'}'>"
                            f"{escape(ov.generation_mode)}</span>"),
    ]))

    _h_htm(html, "B. Requirements", _table_html(
        ["Requirement", "Category", "Coverage", "Tests", "Validation", "Description"],
        [[r.requirement_id, r.category, _coverage_badge(r.coverage_status),
          str(r.test_case_count), escape(r.validation_status), escape(r.description)]
         for r in data.requirements]))

    _h_htm(html, "C. RAG / Knowledge", "")
    html.append("<p class='na'>Corpus: %s · version %s · %d document(s). No semantic quality "
                "metrics are claimed (they are not computed).</p>" % (
                    escape(data.knowledge.corpus_description),
                    escape(data.knowledge.corpus_version),
                    data.knowledge.document_count))
    html.append(_table_html(
        ["Document", "Topic", "Source", "Version"],
        [[escape(d.title), escape(d.topic), escape(d.source), escape(d.version)]
         for d in data.knowledge.documents]))
    html.append("<h3>Requirement → retrieved knowledge</h3>")
    html.append(_table_html(
        ["Requirement", "Retrieval count", "Topics", "Sources"],
        [[m.requirement_id, str(m.retrieval_count),
          escape(", ".join(m.topics) or "Not available"),
          escape(", ".join(m.sources) or "Not available")]
         for m in data.knowledge.requirement_mapping]))

    _h_htm(html, "D. Test Generation",
           f"<p>Total generated: <b>{data.generation.total_generated}</b> · "
           f"mode: <span class='badge {'ok' if data.generation.generation_mode=='MOCK' else 'warn'}'>"
           f"{escape(data.generation.generation_mode)}</span> (never hidden).</p>")
    html.append(_table_html(
        ["Test case", "Requirement", "Category", "Priority", "Generation mode", "Validation"],
        [[t.test_case_id, t.requirement_id, t.category, t.priority,
          _mode_badge(t.generation_mode), escape(t.validation_status)]
         for t in data.generation.tests]))

    _h_htm(html, "E. Test Execution", "")
    html.append(_table_html(
        ["Executed", "PASS", "FAIL", "ERROR", "SKIPPED", "Execution coverage"],
        [[_num(data.execution.total_executed), _num(data.execution.passed),
          _num(data.execution.failed), _num(data.execution.errors),
          _num(data.execution.skipped),
          _pct(data.execution.execution_coverage)]]))
    if data.execution.execution_history:
        html.append("<h3>Execution history</h3>")
        html.append(_table_html(
            ["Test case", "Status", "Execution id"],
            [[escape(h["test_case_id"]), escape(h["status"]), escape(h["execution_id"])]
             for h in data.execution.execution_history]))

    _h_htm(html, "F. Fault Analysis", "")
    html.append(f"<p>Total faults: <b>{_num(data.fault_summary.total_faults)}</b> · "
                f"detected {_num(data.fault_summary.detected_faults)} · "
                f"missed {_num(data.fault_summary.missed_faults)} · "
                f"detection rate {_pct(data.fault_summary.fault_detection_rate)}</p>")
    html.append(_table_html(
        ["Fault", "Type", "Detection", "Injection", "Related tests", "Evidence"],
        [[f.fault_id, f.fault_type, _status_badge(f.detection_status),
          escape(f.injection_status),
          escape(", ".join(f.related_test_case_ids) or "None"),
          escape(f.detection_evidence)]
         for f in data.fault_summary.faults]))

    _h_htm(html, "G. Refinement (Phase 11)", "")
    if data.refinement.available:
        html.append(f"<p>Stop reason: <b>{escape(data.refinement.stop_reason)}</b> · "
                    f"gaps {_num(data.refinement.gaps_before)} → {_num(data.refinement.gaps_after)} · "
                    f"coverage {_pct(data.refinement.coverage_before)} → "
                    f"{_pct(data.refinement.coverage_after)} · "
                    f"improvement {_pct(data.refinement.improvement_requirement_coverage)} · "
                    f"new tests {data.refinement.total_generated} generated / "
                    f"{data.refinement.total_executed} executed.</p>"
                    "<p class='na'>Computed on load in mock mode (read-only, not persisted).</p>")
        html.append(_table_html(
            ["Iter", "Decision", "Gap", "Generated", "Executed", "Cov before", "Cov after", "Improvement"],
            [[str(i.iteration_number), escape(i.decision), escape(i.gap_type),
              str(i.generated), str(i.executed), _pct(i.coverage_before),
              _pct(i.coverage_after), _pct(i.improvement)]
             for i in data.refinement.iterations]))
    else:
        html.append("<p class='na'>Refinement result not available (could not compute).</p>")

    _h_htm(html, "H. Traceability", "")
    html.append(_table_html(
        ["Requirement", "RAG evidence", "Test cases", "Validation", "Executions", "Faults", "Coverage"],
        [[r.requirement_id, str(r.rag_evidence_count),
          escape(", ".join(r.test_case_ids) or "—"),
          escape(r.validation_status),
          escape(", ".join(r.execution_status.split(", ")[:3]) or "—"),
          escape(", ".join(r.fault_types) or "None"),
          _coverage_badge(r.coverage)]
         for r in data.traceability.rows]))
    html.append("<p class='na'>Full real-id links are in <code>reports/final_report.json</code>.</p>")

    _h_htm(html, "I. Final Project Status", "")
    html.append(f"<p>Final test result: {_final_test_htm(data.final_status.final_test_result)}</p>")
    html.append(_table_html(
        ["Phase", "Title", "Status", "Verification"],
        [[str(p.phase_number), escape(p.title), _phase_badge(p.status), escape(p.verification)]
         for p in data.final_status.phases]))
    html.append(f"<p>Requirement coverage <b>{_pct(data.final_status.requirement_coverage)}</b> · "
                f"execution coverage <b>{_pct(data.final_status.execution_coverage)}</b> · "
                f"fault detection <b>{_pct(data.final_status.fault_detection)}</b> · "
                f"remaining gaps <b>{_num(data.final_status.remaining_gaps)}</b></p>")
    if data.final_status.known_limitations:
        html.append("<h3>Known limitations</h3><ul>")
        for lim in data.final_status.known_limitations:
            html.append(f"<li>{escape(lim)}</li>")
        html.append("</ul>")

    html.append("</body></html>")
    return "\n".join(html)


# ------------------------------------------------------------------ TEXT


def render_text(data: vm.DashboardData) -> str:
    ov = data.overview
    lines = []
    lines.append("=" * 78)
    lines.append(ov.project_name)
    lines.append("=" * 78)
    lines.append(f"Status: {ov.project_status} | Phase {ov.current_phase} | "
                 f"{ov.completed_phases}/{ov.total_phases} completed | Mode: {ov.generation_mode}")
    lines.append(f"Requirements: {_num(ov.total_requirements)} | Tests: {_num(ov.total_test_cases)} | "
                 f"Executed: {_num(ov.executed_tests)} | "
                 f"P/F/E/S: {_num(ov.passed)}/{_num(ov.failed)}/{_num(ov.errors)}/{_num(ov.skipped)}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("B. REQUIREMENTS")
    lines.append(f"{'ID':<12}{'Category':<18}{'Coverage':<18}{'Tests':<6}Description")
    for r in data.requirements:
        lines.append(f"{r.requirement_id:<12}{r.category:<18}{r.coverage_status:<18}"
                     f"{r.test_case_count:<6}{r.description[:50]}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("C. RAG / KNOWLEDGE  "
                 f"({data.knowledge.document_count} docs; {len(data.knowledge.retrieved_topics)} topics)")
    for m in data.knowledge.requirement_mapping:
        lines.append(f"  {m.requirement_id}: {m.retrieval_count} chunk(s) "
                     f"-> {', '.join(m.topics) or 'Not available'}")
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"D. TEST GENERATION ({data.generation.total_generated}, mode={data.generation.generation_mode})")
    for t in data.generation.tests:
        lines.append(f"  {t.test_case_id}: {t.category:<12} {t.requirement_id} "
                     f"[{t.generation_mode}] {t.validation_status}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("E. TEST EXECUTION")
    lines.append(f"  executed={_num(data.execution.total_executed)} PASS={_num(data.execution.passed)} "
                 f"FAIL={_num(data.execution.failed)} ERROR={_num(data.execution.errors)} "
                 f"SKIPPED={_num(data.execution.skipped)} coverage={_pct(data.execution.execution_coverage)}")
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"F. FAULT ANALYSIS (total={_num(data.fault_summary.total_faults)} "
                 f"detected={_num(data.fault_summary.detected_faults)} "
                 f"rate={_pct(data.fault_summary.fault_detection_rate)})")
    for f in data.fault_summary.faults:
        lines.append(f"  {f.fault_id:<20} {f.fault_type:<24} {f.detection_status}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("G. REFINEMENT (PHASE 11)")
    if data.refinement.available:
        lines.append(f"  stop={data.refinement.stop_reason} gaps="
                     f"{_num(data.refinement.gaps_before)}->{_num(data.refinement.gaps_after)} "
                     f"cov={_pct(data.refinement.coverage_before)}->{_pct(data.refinement.coverage_after)} "
                     f"imp={_pct(data.refinement.improvement_requirement_coverage)} "
                     f"generated={data.refinement.total_generated} executed={data.refinement.total_executed}")
        for i in data.refinement.iterations:
            lines.append(f"  iter {i.iteration_number}: {i.decision:<18}{i.gap_type:<34} "
                         f"gen={i.generated} cov={_pct(i.coverage_before)}->{_pct(i.coverage_after)}")
    else:
        lines.append("  Not available")
    lines.append("")
    lines.append("-" * 78)
    lines.append("I. FINAL PROJECT STATUS")
    for p in data.final_status.phases:
        lines.append(f"  Phase {p.phase_number:<3} {p.status:<10} {p.title}")
    lines.append(f"  final tests: {data.final_status.final_test_result}")
    lines.append(f"  requirement coverage={_pct(data.final_status.requirement_coverage)} "
                 f"execution={_pct(data.final_status.execution_coverage)} "
                 f"fault detection={_pct(data.final_status.fault_detection)} "
                 f"gaps={_num(data.final_status.remaining_gaps)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- helpers


def _h_htm(html, title, body: str) -> None:
    html.append(f"<h2>{escape(title)}</h2>")
    if body:
        html.append(body)


def _kv_html(pairs) -> str:
    out = ["<div class='kv'>"]
    for k, v in pairs:
        out.append(f"<span>{escape(k)}</span><div>{v}</div>")
    out.append("</div>")
    return "".join(out)


def _table_html(headers, rows) -> str:
    out = ["<table><thead><tr>"]
    for h in headers:
        out.append(f"<th>{escape(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _final_test_htm(d: dict) -> str:
    return (f"total={_num(d.get('total'))} passed={_num(d.get('passed'))} "
            f"failed={_num(d.get('failed'))} errors={_num(d.get('errors'))} "
            f"skipped={_num(d.get('skipped'))}")


def _coverage_badge(status: str) -> str:
    cls = {"COVERED": "ok", "PARTIALLY COVERED": "warn", "UNCOVERED": "bad"}.get(status, "na")
    return f"<span class='badge {cls}'>{escape(status)}</span>"


def _mode_badge(mode: str) -> str:
    cls = "ok" if mode == "MOCK" else "warn"
    return f"<span class='badge {cls}'>{escape(mode)}</span>"


def _status_badge(status: str) -> str:
    cls = {"DETECTED": "ok", "MISSED": "bad", "INJECTED": "ok"}.get(status, "na")
    return f"<span class='badge {cls}'>{escape(status)}</span>"


def _phase_badge(status: str) -> str:
    cls = "ok" if status == "COMPLETE" else "na"
    return f"<span class='badge {cls}'>{escape(status)}</span>"


def _num(v) -> str:
    return str(v) if v is not None else vm.not_available()


def _pct(v) -> str:
    if v is None:
        return vm.not_available()
    return f"{v:.1f}%"


__all__ = ["render_html", "render_text"]
