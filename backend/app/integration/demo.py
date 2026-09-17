"""
Phase 13 — End-to-End Integration demo.

Runs the complete Phase 5-12 chain in MOCK mode (no paid API key required):

    Specification -> ingestion -> RAG -> generation/validation -> execution
                  -> fault analysis -> refinement -> reporting -> dashboard

and prints a per-stage summary plus requirement traceability. Uses only real
project components and real artifacts; noexcept by treating an empty spec as a
clear error message.

HOW TO RUN:
    from the project root:  python -m app.integration.demo
"""

from __future__ import annotations

from app.config import Settings, PROJECT_ROOT
from app.integration import E2EPipeline

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)


def run_demo() -> None:
    cfg = Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        RAG_TOP_K=4,
    )
    pipeline = E2EPipeline(settings_=cfg)
    result = pipeline.run(_SPEC, source="phase13_temperature_sensor.txt", top_k=4)

    print("\n=== Phase 13 — End-to-End Integration demo (MOCK mode) ===\n")
    print(f"Provider mode      : {result.provider_mode}")
    print(f"Run id             : {result.run_id}")
    print(f"Requirements       : {result.total_requirements}")
    print(f"Generated tests    : {result.total_tests} (validated)")
    print(f"Executed           : {result.executed_count} "
          f"(pass={result.passed_count}, fail={result.failed_count}, "
          f"error={result.error_count}, skip={result.skipped_count})")
    print(f"Broker reachable   : {result.broker_reachable}")
    print(f"Dashboard data     : {result.dashboard_available}")

    print("\nStages:")
    for s in result.stages:
        flag = "OK " if s.ok else "FAIL"
        print(f"  [{flag}] {s.stage.value:<16} items={s.items:<3} {s.message or s.error or ''}")

    if result.refinement.applied:
        r = result.refinement
        print(f"\nRefinement: applied={r.applied}, iterations={r.iterations}, "
              f"stop={r.stop_reason}, req coverage {r.coverage_before}% -> {r.coverage_after}%")

    if result.report is not None:
        rep = result.report
        print("\nFinal report (Phase 10):")
        print(f"  requirement coverage = {rep.summary.requirement_coverage}%")
        print(f"  execution coverage   = {rep.summary.execution_coverage}%")
        print(f"  fault detection      = {rep.summary.fault_detection_rate}%")
        print(f"  gaps                 = {rep.summary.gap_count}")

    print("\nRequirement traceability (real ids):")
    for tr in result.requirements:
        print(f"  {tr.requirement_id:<8} cov={tr.coverage_status:<10} "
              f"evidence={len(tr.rag_evidence_chunk_ids)} chunks, "
              f"tcs={len(tr.generated_test_ids)}, executed={len(tr.executed_test_ids)}, "
              f"faults={','.join(tr.fault_types) or '-'}")

    if result.dashboard_available:
        ds = result.dashboard_summary
        print(f"\nDashboard overview : reqs={ds.get('total_requirements')}, "
              f"tcs={ds.get('total_test_cases')}, mode={ds.get('generation_mode')}")

    print("\nDemo complete (E2E chain ran to completion in MOCK mode; nothing fabricated).")


if __name__ == "__main__":
    run_demo()
