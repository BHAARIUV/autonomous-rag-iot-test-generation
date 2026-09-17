"""
Phase 10 — deterministic Final Reporting & Traceability demo.

Runs the real pipeline on the Temperature Sensor / MQTT scenario and produces
the FINAL PROJECT REPORT:

    requirement -> RAG evidence -> test case -> validation -> execution
                 -> fault/result -> coverage -> final traceability

It uses ONLY real project components (ingestion, RAG, mock LLM generation,
Phase 8 execution, Phase 4 faults, Phase 9 analysis, Phase 10 reporting) and
writes:
    reports/final_report.json   (machine-readable, valid JSON)
    reports/final_report.md     (human-readable)

The test summary inside the report is taken from an actual `pytest -q` run
of the project suite (never guessed).

HOW TO RUN:
    from the project root:  python -m app.reporting.demo
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.analysis import AnalysisService
from app.config import Settings, PROJECT_ROOT
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.models import (
    GenerationMetadata,
    TestCase,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.reporting import FinalReportService
from app.reporting.models import FinalTestSummary
from app.testing import ExecutionService, TestActionType, make_action
from app.testing.models import TestStatus

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)
_KNOWN_LIMITATIONS = [
    "Offline suite uses the deterministic mock LLM provider; real OpenAI generation "
    "is wired but not exercised to avoid API spend.",
    "Fault detection is keyed by fault type from execution evidence, not by a "
    "persisted cross-reference to a single injected fault instance.",
    "MQTT tests are honest about broker availability: with no reachable broker they "
    "are SKIPPED (never faked), which lowers interface coverage in broker-less runs.",
]


def _unexecuted_case() -> TestCase:
    return TestCase(
        test_case_id="TC-UNEXEC-001",
        requirement_id="REQ-001",
        title="Generated but never run (coverage gap)",
        objective="Demonstrate a generated-but-never-executed test.",
        category=TestCategory.BOUNDARY,
        priority=TestPriority.HIGH,
        preconditions=[],
        test_steps=[TestStep(step_number=1, action="Drive the device input to exactly -40 C.")],
        expected_result="device accepts -40 C",
        test_data=TestData(inputs={"input": "-40"}, expected={"status": "VALID"}),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def _fault_case() -> TestCase:
    return TestCase(
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
        title="Fault injection: SENSOR_OUT_OF_RANGE",
        objective="Detect an injected out-of-range reading via the range assertion.",
        category=TestCategory.NEGATIVE,
        priority=TestPriority.HIGH,
        preconditions=[],
        test_steps=[
            TestStep(step_number=1, action="Inject a SENSOR_OUT_OF_RANGE fault."),
            TestStep(step_number=2, action="Read the sensor."),
            TestStep(step_number=3, action="Assert the reading is within range."),
        ],
        expected_result="The out-of-range reading fails the assertion.",
        test_data=TestData(),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def _mqtt_case() -> TestCase:
    return TestCase(
        test_case_id="TC-MQTT-001",
        requirement_id="REQ-004",
        title="MQTT publish/validate",
        objective="Verify schema-conforming publication over MQTT.",
        category=TestCategory.COMMUNICATION,
        priority=TestPriority.HIGH,
        preconditions=["MQTT broker reachable."],
        test_steps=[
            TestStep(step_number=1, action="Subscribe to the device topic."),
            TestStep(step_number=2, action="Trigger a device publication."),
            TestStep(step_number=3, action="Validate the received JSON payload against the expected schema."),
        ],
        expected_result="A valid JSON payload arrives on the topic.",
        test_data=TestData(expected={"received": "CONFORMANT"}),
        protocol="MQTT",
        interface="iot/sensor/temperature",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def _run_pytest_summary(cwd: Path, timeout: int = 600) -> FinalTestSummary:
    """Run the project suite and return the REAL pytest tally."""
    py = Path(sys.executable)
    proc = subprocess.run(
        [str(py), "-m", "pytest", "-q", "--disable-warnings"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    try:
        tail = [l for l in out.splitlines() if l.strip()]
        last = tail[-1] if tail else ""
    except Exception:
        last = ""
    return _parse_pytest_line(last, proc.returncode)


def _parse_pytest_line(line: str, rc: int) -> FinalTestSummary:
    import re
    total = passed = failed = errors = skipped = 0
    m = re.search(r"(\d+) passed", line)
    if m:
        passed = int(m.group(1))
    if "failed" in line:
        m = re.search(r"(\d+) failed", line)
        failed = int(m.group(1)) if m else failed
    if "error" in line.lower() and "errors" in line:
        m = re.search(r"(\d+) error", line)
        errors = int(m.group(1)) if m else 0
    if "skipped" in line:
        m = re.search(r"(\d+) skipped", line)
        skipped = int(m.group(1)) if m else 0
    total = passed + failed + errors + skipped
    duration = 0.0
    dm = re.search(r"in ([\d.]+)s", line)
    if dm:
        duration = float(dm.group(1))
    return FinalTestSummary(
        total=total, passed=passed, failed=failed, errors=errors,
        skipped=skipped, duration_seconds=duration,
    )


def run_demo(print_pipeline: bool = True) -> None:
    cfg = Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        RAG_TOP_K=4,
    )
    rag = RagService(settings_=cfg)
    rag.index_knowledge_base()
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)

    # --- Specification -> Requirements (Phase 5) -------------------------
    spec = ingest_text(_SPEC, source="temperature_sensor.txt")
    requirements = spec.requirements
    requirement = {r.requirement_id: r for r in requirements}["REQ-001"]

    # --- RAG evidence -> Generated Test Cases (Phase 6/7) -----------------
    suite = generator.generate_for_requirement(requirement, top_k=4)
    test_cases = list(suite.test_cases)

    # --- Execution (Phase 8) ----------------------------------------------
    results, _ = executor.execute_test_cases(suite.test_cases)

    # --- Fault injection / results (Phase 4/8) ----------------------------
    fault_case = _fault_case()
    fault_result = executor.execute_actions(
        [
            make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
            make_action(TestActionType.READ_SENSOR),
            make_action(TestActionType.ASSERT_RANGE),
        ],
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
    )
    results.append(fault_result)

    mqtt_case = _mqtt_case()
    mqtt_result = executor.execute_test_case(mqtt_case)
    results.append(mqtt_result)

    all_test_cases = test_cases + [_unexecuted_case(), fault_case, mqtt_case]

    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISCONNECT"),
    ]

    # --- Coverage & Fault Analysis (Phase 9) ------------------------------
    analysis = AnalysisService.analyze_execution_results(
        requirements, all_test_cases, results, known_faults
    )

    # --- Final project report (Phase 10) ----------------------------------
    test_summary = _run_pytest_summary(PROJECT_ROOT)
    report = FinalReportService.generate_final_report(
        requirements=requirements,
        test_cases=all_test_cases,
        results=results,
        fault_specs=known_faults,
        test_summary=test_summary,
        known_limitations=_KNOWN_LIMITATIONS,
    )

    report_dir = PROJECT_ROOT / "reports"
    json_path = FinalReportService.write_json_report(
        report, report_dir / "final_report.json"
    )
    md_path = FinalReportService.write_markdown_report(
        report, report_dir / "final_report.md"
    )

    if print_pipeline:
        _print_pipeline(
            requirement, suite.test_cases, results, fault_result, mqtt_result,
            analysis, report, json_path, md_path,
        )
    rag.close()


def _print_pipeline(requirement, generated, results, fault_result, mqtt_result,
                    analysis, report, json_path, md_path) -> None:
    print("\n=== Phase 10 — Final Reporting & Traceability demo ===\n")
    print(f"Specification  : temperature_sensor.txt")
    print(f"Requirement    : {requirement.requirement_id} [{requirement.category.value}]")
    print(f"  RAG topics   : {sorted({c.topic for tc in generated if tc.source_context for c in tc.source_context.chunks})}")
    print(f"Generated      : {len(generated)} test case(s)  (mock, validated)")
    print(f"Executed       : {len([r for r in results if r.status in (TestStatus.PASS, TestStatus.FAIL)])}")
    fault_label = (
        f"{fault_result.status.value} (SENSOR_OUT_OF_RANGE injected + detected)"
        if fault_result.status is TestStatus.FAIL
        else f"{fault_result.status.value}"
    )
    print(f"Fault result   : {fault_label}")
    print(f"MQTT result    : {mqtt_result.status.value}")
    print(f"Coverage       : requirement={report.summary.requirement_coverage}% "
          f"execution={report.summary.execution_coverage}% "
          f"fault_detection={report.summary.fault_detection_rate}% gaps={report.summary.gap_count}")
    print(f"\nTest suite (real pytest): {report.test_summary.total} total, "
          f"{report.test_summary.passed} passed, {report.test_summary.failed} failed, "
          f"{report.test_summary.skipped} skipped\n")
    print(f"Wrote JSON    : {json_path}")
    print(f"Wrote Markdown: {md_path}")
    print()


if __name__ == "__main__":
    run_demo()
