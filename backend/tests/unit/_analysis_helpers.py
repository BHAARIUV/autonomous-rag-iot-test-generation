"""
Phase 9 test helpers — build trusted Phase 5/7/8/4 objects with known values
so every coverage calculation is exercised against a small, deterministic
dataset.
"""

from __future__ import annotations

from app.faults import FaultType, make_fault
from app.ingestion.models import Constraint, Requirement, RequirementCategory, RequirementSeverity
from app.llm.models import (
    GenerationMetadata,
    TestCategory,
    TestCase,
    TestData,
    TestPriority,
    TestStep,
)
from app.testing.models import (
    EnvironmentSnapshot,
    ExecutionResult,
    SimulatorStateSnapshot,
    StepEvidence,
    StepOutcome,
    TestStatus,
)

_META = GenerationMetadata(
    provider="mock", model="mock", generation_mode="mock",
    prompt_version="test", timestamp="test",
)


def make_requirement(
    rid: str,
    category: RequirementCategory = RequirementCategory.RANGE,
    *,
    min_c: float | None = -40.0,
    max_c: float | None = 125.0,
) -> Requirement:
    constraints = []
    if min_c is not None:
        constraints.append(Constraint(kind="min", value=str(min_c), unit="°C"))
    if max_c is not None:
        constraints.append(Constraint(kind="max", value=str(max_c), unit="°C"))
    return Requirement(
        requirement_id=rid,
        description=f"Requirement {rid}",
        category=category,
        constraints=constraints,
        severity=RequirementSeverity.MEDIUM,
        source="test.txt",
        source_reference="line 1",
    )


def make_test_case(
    tc_id: str,
    rid: str,
    category: TestCategory = TestCategory.POSITIVE,
    *,
    protocol: str = "SENSOR",
    interface: str | None = None,
    steps: list[str] | None = None,
) -> TestCase:
    return TestCase(
        test_case_id=tc_id,
        requirement_id=rid,
        title=tc_id,
        objective="test",
        category=category,
        priority=TestPriority.MEDIUM,
        preconditions=[],
        test_steps=[
            TestStep(step_number=i + 1, action=text)
            for i, text in enumerate(steps or ["Observe the reported value."])
        ],
        expected_result="ok",
        test_data=TestData(inputs={"input": "0"}, expected={"status": "OK"}),
        protocol=protocol,
        interface=interface,
        generation_metadata=_META,
    )


def make_result(
    tc_id: str,
    rid: str,
    status: TestStatus,
    *,
    injected_fault_types: list[FaultType] | None = None,
) -> ExecutionResult:
    evidence: list[StepEvidence] = []
    for ft in injected_fault_types or []:
        evidence.append(
            StepEvidence(
                step_number=len(evidence) + 1,
                action="INJECT_FAULT",
                source_step_text="Inject fault.",
                action_result=StepOutcome.OK,
                expected=f"inject {ft.value}",
                observed="active",
            )
        )
    return ExecutionResult(
        test_case_id=tc_id,
        requirement_id=rid,
        status=status,
        steps_executed=len(evidence) or 1,
        steps_passed=1 if status is TestStatus.PASS else 0,
        steps_failed=1 if status is TestStatus.FAIL else 0,
        failure_reason=("assertion failed" if status is TestStatus.FAIL else None),
        error_message=("boom" if status is TestStatus.ERROR else None),
        execution_evidence=evidence,
        environment=EnvironmentSnapshot(),
        simulator_state=SimulatorStateSnapshot(
            device_name="Temperature Sensor",
            status=None,
            tick_count=0,
            min_temperature_c=-40.0,
            max_temperature_c=125.0,
            accuracy_c=0.5,
            seed=42,
        ),
        mqtt_information=None,
    )


def make_known_faults(*types: FaultType, prefix: str = "F") -> list:
    return [
        make_fault(ft, fault_id=f"{prefix}-{ft.value}")
        for ft in types
    ]
