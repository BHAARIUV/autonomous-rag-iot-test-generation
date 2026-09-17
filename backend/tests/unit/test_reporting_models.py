"""
Phase 10 — Final Reporting model unit tests.

Covers the typed, frozen models that make up the FinalProjectReport and the
enums that encode evidence-backed states (Phase status, anomaly/validation/
injection/fault status).
"""

from __future__ import annotations

from datetime import timezone

import pytest

from app.analysis.models import CoverageGap, CoverageSummary
from app.reporting import models as m


class TestEnums:
    def test_phase_status_members(self):
        assert m.PhaseStatus.COMPLETE.value == "COMPLETE"
        assert m.PhaseStatus.PENDING.value == "PENDING"

    def test_fault_detection_status_members(self):
        assert m.FaultDetectionStatus.DETECTED.value == "DETECTED"
        assert m.FaultDetectionStatus.MISSED.value == "MISSED"
        assert m.FaultDetectionStatus.NOT_EXECUTED.value == "NOT_EXECUTED"
        assert m.FaultDetectionStatus.NOT_APPLICABLE.value == "NOT_APPLICABLE"

    def test_injection_status_members(self):
        assert m.InjectionStatus.INJECTED.value == "INJECTED"
        assert m.InjectionStatus.NOT_EXECUTED.value == "NOT_EXECUTED"

    def test_validation_status_members(self):
        assert m.ValidationStatus.VALIDATED.value == "VALIDATED"
        assert m.ValidationStatus.REJECTED.value == "REJECTED"
        assert m.ValidationStatus.PENDING.value == "PENDING"


class TestPhaseEntry:
    def test_defaults_and_flag(self):
        p = m.PhaseEntry(
            phase_number=1,
            title="Setup",
            status=m.PhaseStatus.COMPLETE,
            major_feature="skel",
            verification="tests",
        )
        assert p.phase_number == 1

    def test_phase_number_must_be_positive(self):
        with pytest.raises(Exception):
            m.PhaseEntry(
                phase_number=0,
                title="x",
                status=m.PhaseStatus.COMPLETE,
                major_feature="x",
                verification="x",
            )


class TestTraceabilityModels:
    def test_rag_evidence_round_trip(self):
        e = m.RagEvidence(
            chunk_id="chunk-1", document_id="doc-1", source="spec.txt",
            topic="boundary", relevance=0.9,
        )
        assert e.relevance == 0.9

    def test_rag_evidence_constrains_relevance(self):
        with pytest.raises(Exception):
            m.RagEvidence(
                chunk_id="c", document_id="d", source="s", topic="t", relevance=2.0
            )

    def test_test_case_traceability_defaults(self):
        t = m.TestCaseTraceability(
            test_case_id="TC-1",
            requirement_id="REQ-1",
            category="POSITIVE",
            priority="MEDIUM",
            has_executed=False,
        )
        assert t.validation_status is m.ValidationStatus.VALIDATED
        assert t.rag_evidence == []
        assert t.executions == []
        assert t.final_status is None

    def test_fault_traceability_defaults(self):
        f = m.FaultTraceability(
            fault_id="F-1",
            fault_type="SENSOR_OUT_OF_RANGE",
            injection_status=m.InjectionStatus.NOT_EXECUTED,
            detection_status=m.FaultDetectionStatus.NOT_EXECUTED,
            detection_evidence="n/a",
        )
        assert f.requirement_ids == []
        assert f.related_test_case_ids == []
        assert f.injection_evidence == []
        assert f.execution_result is None


class TestFinalTestSummary:
    def test_counts(self):
        s = m.FinalTestSummary(total=5, passed=5, failed=0, errors=0, skipped=0)
        assert s.total == 5

    def test_negative_count_rejected(self):
        with pytest.raises(Exception):
            m.FinalTestSummary(total=-1, passed=0, failed=0, errors=0, skipped=0)


class TestFinalProjectReport:
    def test_default_identifiers(self):
        r = m.FinalProjectReport(
            coverage=_coverage(),
            test_summary=_test_summary(),
            summary=_summary(),
        )
        assert r.project_id == "autonomous-rag-iot-test-generation"
        assert r.status == "COMPLETE"
        assert len(r.analysis_id) == 32

    def test_default_collections_are_empty(self):
        r = m.FinalProjectReport(
            coverage=_coverage(),
            test_summary=_test_summary(),
            summary=_summary(),
        )
        assert r.phases == []
        assert r.requirements == []
        assert r.faults == []
        assert r.gaps == []

    def test_timestamp_is_utc_aware(self):
        r = m.FinalProjectReport(
            coverage=_coverage(),
            test_summary=_test_summary(),
            summary=_summary(),
        )
        assert r.generated_timestamp.tzinfo is not None
        assert r.generated_timestamp.tzinfo == timezone.utc

    def test_json_serializable(self):
        r = m.FinalProjectReport(
            coverage=_coverage(),
            test_summary=_test_summary(),
            summary=_summary(),
            gaps=[CoverageGap(
                gap_id="GAP-1", type="FAULT_NO_TEST", severity="HIGH",
                description="no test", recommended_action="add a test",
            )],
        )
        data = r.model_dump(mode="json")
        import json

        json.dumps(data)
        assert data["coverage"]["requirement_coverage"] == 50.0


def _coverage() -> CoverageSummary:
    return CoverageSummary(
        total_requirements=4,
        covered_requirements=2,
        requirement_coverage=50.0,
        total_test_cases=9,
        executed_test_cases=8,
        execution_coverage=88.89,
        pass_rate=77.78,
        total_faults=2,
        detected_faults=1,
        fault_detection_rate=100.0,
        gap_count=1,
    )


def _test_summary() -> m.FinalTestSummary:
    return m.FinalTestSummary(total=10, passed=10, failed=0, errors=0, skipped=0)


def _summary() -> m.FinalProjectSummary:
    return m.FinalProjectSummary(
        project_id="autonomous-rag-iot-test-generation",
        requirement_count=4,
        test_case_count=9,
        executed_test_count=8,
        passed_count=7,
        failed_count=1,
        error_count=0,
        skipped_count=0,
        execution_coverage=88.89,
        requirement_coverage=50.0,
        fault_count=2,
        detected_fault_count=1,
        fault_detection_rate=100.0,
        gap_count=1,
    )
