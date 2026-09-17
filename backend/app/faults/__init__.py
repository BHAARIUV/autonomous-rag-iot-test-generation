"""
Phase 4 — Fault Injection Engine.

Public API used by later phases and tests:

    FaultInjector                     - decision/history engine
    FaultInjectedSimulator            - simulator-side fault adapter
    FaultInjectingPublisher           - MQTT-side fault interceptor
    FaultRegistry / make_fault        - canonical fault factory
    FaultType / FaultSeverity /
    FaultImpact / FaultSpec / ...     - structured fault model
"""

from app.faults.engine import FaultInjector
from app.faults.mqtt_interceptor import FaultInjectingPublisher
from app.faults.models import (
    ExpectedDetection,
    FaultImpact,
    FaultParams,
    FaultRecord,
    FaultSeverity,
    FaultSpec,
    FaultType,
    InjectionCondition,
)
from app.faults.registry import FaultRegistry, make_fault
from app.faults.simulator_adapter import FaultInjectedSimulator

__all__ = [
    "ExpectedDetection",
    "FaultImpact",
    "FaultInjectingPublisher",
    "FaultInjector",
    "FaultParams",
    "FaultRecord",
    "FaultRegistry",
    "FaultSeverity",
    "FaultSpec",
    "FaultType",
    "FaultInjectedSimulator",
    "InjectionCondition",
    "make_fault",
]