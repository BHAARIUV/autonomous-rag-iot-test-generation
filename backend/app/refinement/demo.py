"""
Phase 11 — interactive demo of the Autonomous Test-Refinement Loop.

Builds the Temperature Sensor scenario with an intentionally INCOMPLETE initial
suite (only REQ-001 generated + executed; REQ-002/003/004 uncovered), then lets
the refinement loop close the gap automatically:

    initial results -> analysis -> select gap -> RAG-aware generate
    -> validate -> execute -> re-analyse -> compare before/after
    -> repeat until TARGET reached / max iterations / no improvement...

Everything reported is derived from the REAL Phase 5-9 artifacts and the REAL
Phase 11 loop — no numbers are fabricated.

HOW TO RUN:
    from the project root:  python -m app.refinement.demo
"""

from __future__ import annotations

from app.config import Settings
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.refinement import RefinementService, StopReason
from app.testing import ExecutionService

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)


def run_demo() -> None:
    cfg = Settings(_env_file=None, LLM_PROVIDER="mock", LLM_MODEL="mock-llm",
                   EMBEDDING_PROVIDER="local", EMBEDDING_DIMENSION=256,
                   RAG_TOP_K=4)
    rag = RagService(settings_=cfg)
    rag.index_knowledge_base()
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)

    spec = ingest_text(_SPEC, source="temperature_sensor.txt")
    reqs = spec.requirements

    # --- DELIBERATELY incomplete initial suite: only REQ-001 -----------------
    req1 = {r.requirement_id: r for r in reqs}["REQ-001"]
    suite = generator.generate_for_requirement(req1, top_k=4)
    results, _ = executor.execute_test_cases(suite.test_cases)

    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISC"),
    ]

    service = RefinementService(
        settings_=cfg, generator=generator, executor=executor,
        max_iterations=6, min_improvement=0.0,
        target_requirement_coverage=90.0,
    )
    result = service.run(
        requirements=reqs,
        test_cases=suite.test_cases,
        results=results,
        fault_specs=known_faults,
    )

    _print_result(result, reqs, suite.test_cases, results, known_faults)
    rag.close()


def _print_result(result, reqs, initial_tcs, initial_results, known_faults) -> None:
    print("\n=== Phase 11 — Autonomous Test-Refinement Loop ===\n")
    print(f"requirements        : {len(reqs)}  ({', '.join(r.requirement_id for r in reqs)})")
    print(f"initial suite       : {len(initial_tcs)} test(s) generated for REQ-001 only; "
          f"{len(initial_results)} executed")
    print(f"known faults        : {len(known_faults)} registered")
    print()

    i = result.initial_coverage
    f = result.final_coverage
    print("--- Coverage: BEFORE vs AFTER ---")
    print(f"  requirement coverage : {i.requirement_coverage}% -> {f.requirement_coverage}%")
    print(f"  executed test cases  : {i.executed_test_cases}/{i.total_test_cases} -> {f.executed_test_cases}/{f.total_test_cases}")
    print(f"  execution coverage   : {i.execution_coverage}% -> {f.execution_coverage}%")
    print(f"  fault detection      : {i.fault_detection_rate}% -> {f.fault_detection_rate}%")
    print(f"  remaining gaps       : {i.gap_count} -> {f.gap_count}")
    print()

    print("--- Iterations ---")
    for it in result.iterations:
        gap = it.selected_gap.gap_type if it.selected_gap else "n/a"
        print(
            f"  iter {it.iteration_number}: [{it.decision.value:<18}] "
            f"{gap:<32} gen={len(it.generated_test_case_ids):>2} "
            f"exec={len(it.executed_ids):>2} "
            f"cov {it.coverage_before.requirement_coverage}%->"
            f"{it.coverage_after.requirement_coverage}% imp={it.improvement}"
        )
    print()

    print("--- Stop ---")
    print(f"  stop_reason : {result.stop_reason.value}")
    print(f"  detail      : {result.stop_detail}")
    print(f"  new tests   : {result.total_generated} generated, {result.total_executed} executed")
    print(f"  improvement : req_coverage +{result.improvement_requirement_coverage}%, "
          f"execution +{result.improvement_execution_coverage}%, "
          f"fault_detection +{result.improvement_fault_detection}%")
    print()


if __name__ == "__main__":
    run_demo()
