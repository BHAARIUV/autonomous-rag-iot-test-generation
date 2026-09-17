"""
LLM provider abstraction for the Phase 7 test generator.

WHAT:
    - `LLMProvider`        — small abstract interface: `generate(system_prompt,
      user_prompt) -> str`, returning the raw structured JSON the generator
      will parse and validate.
    - `MockLLMProvider`    — deterministic, offline provider. It reads the
      machine-readable `<requirement_json>` and `<knowledge_topics>` blocks
      written by the prompt builder and derives test cases from the actual
      requirement constraints and retrieved topics. It never calls a network,
      never needs an API key, and produces logically different output for
      different requirements.
    - `OpenAILLMProvider`  — real provider using the existing LLM_* settings;
      lazy-imports the `openai` package, raises `LLMUnavailableError` if the
      call can't be made, and never logs or stores the API key.
    - `create_llm_provider(settings_)` — factory honoring the existing
      `settings.is_mock_llm` convention: no API key => MOCK mode, exactly like
      `app/main.py` reports. An explicitly unknown provider with a key raises
      a clear `LLMConfigurationError`.

WHY:
    The generator must not be coupled to one vendor. MOCK mode keeps the whole
    test suite runnable offline (a hard project requirement).

HOW TO VERIFY:
    See tests/unit/test_llm_providers.py and tests/unit/test_llm_mock.py.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from loguru import logger

from app.llm.errors import LLMConfigurationError, LLMUnavailableError

_REQ_JSON_BLOCK = re.compile(r"<requirement_json>\s*(.*?)\s*</requirement_json>", re.S)
_TOPICS_BLOCK = re.compile(r"<knowledge_topics>\s*(.*?)\s*</knowledge_topics>", re.S)

_SENSOR_PROTOCOL_TOPICS = {"temperature_sensor_testing", "sensor_accuracy"}


class LLMProvider(ABC):
    """Common interface every test-generation LLM provider implements."""

    name: str = "abstract"
    generation_mode: str = "llm"  # subclass: "mock" or "llm"
    model: str = ""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the raw structured JSON text produced for the prompts."""


# ---------------------------------------------------------------------------
# MOCK provider (deterministic, offline)
# ---------------------------------------------------------------------------


def _render_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.10g}"


class MockLLMProvider(LLMProvider):
    """Deterministic local generator. Derives tests from the requirement's
    constraints, category and the retrieved knowledge topics, so different
    requirements produce different (but reproducible) test sets."""

    name = "mock"
    generation_mode = "mock"
    model = "mock-llm"

    def __init__(self, settings_=None):
        self._settings = settings_

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        requirement = self._extract_requirement(user_prompt)
        topics = self._extract_topics(user_prompt)
        tests = self._derive_tests(requirement, topics)
        payload = {
            "summary": (
                f"MOCK: {len(tests)} test case(s) derived deterministically "
                f"from requirement {requirement.get('id', '')}"
            ),
            "test_cases": tests,
        }
        return json.dumps(payload, ensure_ascii=False)

    # ------------------------------------------------------------------ parsing

    def _extract_requirement(self, user_prompt: str) -> dict:
        match = _REQ_JSON_BLOCK.search(user_prompt)
        if not match:
            logger.warning("MockLLMProvider: no <requirement_json> block found")
            return {}
        try:
            data = json.loads(match.group(1))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            logger.warning("MockLLMProvider: <requirement_json> block is not JSON")
            return {}

    def _extract_topics(self, user_prompt: str) -> set[str]:
        match = _TOPICS_BLOCK.search(user_prompt)
        if not match:
            return set()
        return {t.strip() for t in match.group(1).split(",") if t.strip()}

    # ------------------------------------------------------------ derivation

    def _derive_tests(self, requirement: dict, topics: set[str]) -> list[dict]:
        category = (requirement.get("category") or "").upper()
        description = requirement.get("description") or ""
        rid = requirement.get("id") or ""
        constraints: list[dict] = requirement.get("constraints") or []

        unit = next((c.get("unit") or "" for c in constraints if c.get("unit")), "")
        values: dict[str, float] = {}
        for c in constraints:
            try:
                values[c["kind"]] = float(c["value"])
            except (KeyError, ValueError, TypeError):
                pass
        vmin = values.get("min")
        vmax = values.get("max")
        single = values.get("value")
        rate = values.get("rate")

        protocol = (
            "MQTT"
            if category == "COMMUNICATION"
            or "mqtt" in description.lower()
            or "communicat" in description.lower()
            else "SENSOR"
        )
        interface = "iot/sensor/temperature" if protocol == "MQTT" else None

        numeric = vmin is not None or vmax is not None or single is not None or rate is not None
        nominal = self._nominal(vmin=vmin, vmax=vmax, single=single, rate=rate)

        tests: list[dict] = []
        seen_titles: set[str] = set()

        def _add(
            test_category,
            title,
            objective,
            steps,
            expected,
            inputs,
            expected_data,
            preconditions,
            assumptions,
            priority,
        ) -> None:
            dedup_key = (test_category, title)
            if dedup_key in seen_titles:
                return
            seen_titles.add(dedup_key)
            tests.append(
                {
                    "test_case_id": "",
                    "requirement_id": rid,
                    "title": title,
                    "objective": objective,
                    "category": test_category,
                    "priority": priority,
                    "preconditions": preconditions,
                    "test_steps": steps,
                    "expected_result": expected,
                    "test_data": {
                        "description": "Inputs and expected values",
                        "inputs": inputs,
                        "expected": expected_data,
                    }
                    if inputs or expected_data
                    else None,
                    "protocol": protocol,
                    "interface": interface,
                    "assumptions": list(assumptions),
                }
            )

        want_boundary = numeric and (category in {"RANGE", "ACCURACY"} or "boundary_value_analysis" in topics)
        want_negative = numeric and ("negative_testing" in topics or category in {"RANGE", "NEGATIVE", "ACCURACY"})
        want_equivalence = numeric and "equivalence_partitioning" in topics
        want_timing = rate is not None or category == "TIMING" or "timing_sampling" in topics or unit in {"s", "ms"}
        want_communication = category == "COMMUNICATION" or "mqtt" in description.lower() or bool(topics & {"mqtt_testing", "communication_reliability"})
        want_data_validation = category == "DATA_VALIDATION" or "data_validation" in topics
        want_reliability = category in {"RELIABILITY", "SAFETY"} or bool(topics & {"device_offline_recovery", "fault_injection"})

        step = 0.1

        # POSITIVE: a realistic nominal success path first.
        if nominal is not None and category in {"RANGE", "ACCURACY"}:
            _add(
                "POSITIVE",
                f"Nominal operating value {_render_number(nominal)} {unit}".strip(),
                "Verify the device reports a nominal in-range value correctly.",
                [
                    {"step_number": 1, "action": "Set the device input to the nominal value within the declared operating envelope."},
                    {"step_number": 2, "action": "Trigger a measurement."},
                    {"step_number": 3, "action": "Observe the reported value and device status."},
                ],
                "Device accepts the value and reports it without an error or fault.",
                {"input": _render_number(nominal), "unit": unit},
                {"status": "OK"},
                [f"Device is powered and connected ({protocol})."],
                (),
                "MEDIUM",
            )
        else:
            _add(
                "POSITIVE",
                "Normal functional operation",
                "Verify the device performs its primary function correctly under normal conditions.",
                [
                    {"step_number": 1, "action": "Exercise the device through its normal operating path."},
                    {"step_number": 2, "action": "Confirm the output matches the required behavior."},
                ],
                "Device completes the normal operation successfully.",
                {},
                {"result": "SUCCESS"},
                [f"Device is powered and connected ({protocol})."],
                (),
                "MEDIUM",
            )

        if want_boundary:
            if vmin is not None:
                _add(
                    "BOUNDARY",
                    f"Minimum boundary value {_render_number(vmin)} {unit}".strip(),
                    "Verify the minimum bound of the declared range is accepted.",
                    [
                        {"step_number": 1, "action": f"Drive the device input to exactly {_render_number(vmin)} {unit}.".strip()},
                        {"step_number": 2, "action": "Trigger a measurement and read the result."},
                    ],
                    "Device accepts the minimum boundary value as valid.",
                    {"input": _render_number(vmin), "unit": unit},
                    {"status": "VALID", "edge": "MIN"},
                    [],
                    (),
                    "HIGH",
                )
            if vmax is not None:
                _add(
                    "BOUNDARY",
                    f"Maximum boundary value {_render_number(vmax)} {unit}".strip(),
                    "Verify the maximum bound of the declared range is accepted.",
                    [
                        {"step_number": 1, "action": f"Drive the device input to exactly {_render_number(vmax)} {unit}.".strip()},
                        {"step_number": 2, "action": "Trigger a measurement and read the result."},
                    ],
                    "Device accepts the maximum boundary value as valid.",
                    {"input": _render_number(vmax), "unit": unit},
                    {"status": "VALID", "edge": "MAX"},
                    [],
                    (),
                    "HIGH",
                )
            if single is not None:
                _add(
                    "BOUNDARY",
                    f"Accuracy limit +{_render_number(single)}{unit}".strip(),
                    "Verify a deviation equal to the accuracy limit is accepted.",
                    [
                        {"step_number": 1, "action": f"Set up a deviation of +{_render_number(single)} {unit} from the true value.".strip()},
                        {"step_number": 2, "action": "Read the reported value."},
                    ],
                    "Device reports a value within the accuracy limit.",
                    {"deviation": f"+{_render_number(single)}", "unit": unit},
                    {"deviation_accepted": "YES"},
                    [],
                    (),
                    "HIGH",
                )

        if want_negative:
            if vmin is not None:
                below = vmin - step
                _add(
                    "NEGATIVE",
                    f"Just below minimum {_render_number(below)} {unit}".strip(),
                    "Verify a value below the declared minimum is rejected.",
                    [
                        {"step_number": 1, "action": f"Drive the device input to {_render_number(below)} {unit}, below the minimum.".strip()},
                        {"step_number": 2, "action": "Trigger a measurement and check the device response."},
                    ],
                    "Device rejects the out-of-range value and reports an error/out-of-range condition.",
                    {"input": _render_number(below), "unit": unit},
                    {"status": "INVALID", "reason": "BELOW_MIN"},
                    [],
                    (),
                    "HIGH",
                )
            if vmax is not None:
                above = vmax + step
                _add(
                    "NEGATIVE",
                    f"Just above maximum {_render_number(above)} {unit}".strip(),
                    "Verify a value above the declared maximum is rejected.",
                    [
                        {"step_number": 1, "action": f"Drive the device input to {_render_number(above)} {unit}, above the maximum.".strip()},
                        {"step_number": 2, "action": "Trigger a measurement and check the device response."},
                    ],
                    "Device rejects the out-of-range value and reports an error/out-of-range condition.",
                    {"input": _render_number(above), "unit": unit},
                    {"status": "INVALID", "reason": "ABOVE_MAX"},
                    [],
                    (),
                    "HIGH",
                )
            if single is not None:
                over = single + step
                _add(
                    "NEGATIVE",
                    f"Exceeds accuracy limit +{_render_number(over)} {unit}".strip(),
                    "Verify a deviation beyond the accuracy limit is flagged.",
                    [
                        {"step_number": 1, "action": f"Set up a deviation of +{_render_number(over)} {unit} from the true value.".strip()},
                        {"step_number": 2, "action": "Read the reported value and any accuracy warning."},
                    ],
                    "Device flags the reading as out of specification.",
                    {"deviation": f"+{_render_number(over)}", "unit": unit},
                    {"deviation_accepted": "NO"},
                    [],
                    (),
                    "HIGH",
                )

        if want_equivalence and vmin is not None and vmax is not None:
            interior = vmin + step
            _add(
                "EQUIVALENCE",
                f"Valid partition representative {_render_number(interior)} {unit}".strip(),
                "Verify a value just inside the valid partition is treated as valid.",
                [
                    {"step_number": 1, "action": f"Drive the device input to {_render_number(interior)} {unit} (inside valid partition).".strip()},
                    {"step_number": 2, "action": "Trigger a measurement and read the result."},
                ],
                "Device classifies the value as valid and reports it.",
                {"input": _render_number(interior), "unit": unit},
                {"partition": "VALID"},
                [],
                (),
                "MEDIUM",
            )

        if want_timing and (rate is not None or category == "TIMING"):
            interval = rate if rate is not None else 1.0
            _add(
                "TIMING",
                f"Measurement at declared interval {_render_number(interval)} s".strip(),
                "Verify the device produces a measurement every declared interval.",
                [
                    {"step_number": 1, "action": "Start the sampling clock."},
                    {"step_number": 2, "action": f"Wait one declared interval ({_render_number(interval)} s).".strip()},
                    {"step_number": 3, "action": "Confirm a fresh measurement was produced."},
                ],
                "A new measurement is produced at the declared interval.",
                {"interval_s": _render_number(interval)},
                {"reading_produced": "YES"},
                ["Device is enabled and idle."],
                (),
                "HIGH",
            )
            _add(
                "TIMING",
                "Sampling faster than the declared interval",
                "Verify the device does not produce measurements faster than declared.",
                [
                    {"step_number": 1, "action": "Record the timestamps of consecutive readings."},
                    {"step_number": 2, "action": f"Assert the gap is not shorter than {_render_number(interval)} s.".strip()},
                ],
                "No measurement is produced before the declared interval elapses.",
                {},
                {"min_gap_seconds": _render_number(interval)},
                [],
                (),
                "LOW",
            )

        if want_communication:
            _add(
                "COMMUNICATION",
                "Publish a valid payload on the topic",
                "Verify the device publishes a schema-conforming payload on its configured topic.",
                [
                    {"step_number": 1, "action": "Subscribe to the device topic."},
                    {"step_number": 2, "action": "Trigger a device publication."},
                    {"step_number": 3, "action": "Validate the received JSON payload against the expected schema."},
                ],
                "A valid JSON payload arrives on the topic matching the expected schema.",
                {},
                {"received": "CONFORMANT", "qos": "1"},
                [f"MQTT broker is reachable ({protocol})."],
                (),
                "HIGH",
            )
            _add(
                "COMMUNICATION",
                "QoS 1 delivery is acknowledged",
                "Verify QoS 1 messages are delivered at least once and acknowledged.",
                [
                    {"step_number": 1, "action": "Publish a message with QoS 1."},
                    {"step_number": 2, "action": "Confirm the PUBACK / delivery acknowledgement."},
                ],
                "Every QoS 1 message is acknowledged and delivered at least once.",
                {},
                {"delivery": "AT_LEAST_ONCE"},
                ["MQTT broker is reachable."],
                (),
                "MEDIUM",
            )

        if want_reliability:
            _add(
                "RELIABILITY",
                "Offline device buffers and reconnects",
                "Verify the device buffers data while offline and flushes it after reconnect.",
                [
                    {"step_number": 1, "action": "Take the device offline / disconnect it from the network."},
                    {"step_number": 2, "action": "Let it capture measurements during the outage."},
                    {"step_number": 3, "action": "Bring the network back and observe reconnection."},
                    {"step_number": 4, "action": "Confirm buffered readings are flushed to the broker."},
                ],
                "Device reconnects automatically and delivers all buffered readings.",
                {},
                {"flushed_total": "ALL_BUFFERED"},
                ["Network outage is simulated."],
                ("A temporary outage is expected to be survivable.",),
                "HIGH",
            )

        if want_data_validation:
            _add(
                "DATA_VALIDATION",
                "Schema-conforming payload accepted",
                "Verify a full, schema-conforming payload is accepted.",
                [
                    {"step_number": 1, "action": "Send a complete, typed payload."},
                    {"step_number": 2, "action": "Check the device accepts it."},
                ],
                "Device accepts the conforming payload without error.",
                {},
                {"accepted": "YES"},
                [],
                (),
                "MEDIUM",
            )
            _add(
                "DATA_VALIDATION",
                "Malformed payload rejected",
                "Verify a type-mismatched or malformed payload is rejected, not accepted.",
                [
                    {"step_number": 1, "action": "Send a payload with a wrong field type / missing field."},
                    {"step_number": 2, "action": "Check the device response."},
                ],
                "Device rejects the malformed payload and logs an error.",
                {},
                {"accepted": "NO", "error": "INVALID_PAYLOAD"},
                [],
                ("The exact rejection signal depends on the device interface.",),
                "MEDIUM",
            )

        return tests[:8]

    @staticmethod
    def _nominal(*, vmin, vmax, single, rate) -> float | None:
        if vmin is not None and vmax is not None:
            return (vmin + vmax) / 2.0
        if single is not None:
            return single
        if vmin is not None:
            return vmin + 1.0
        if vmax is not None:
            return vmax - 1.0
        if rate is not None:
            return rate
        return None


# ---------------------------------------------------------------------------
# REAL provider (OpenAI, used only when an API key is configured)
# ---------------------------------------------------------------------------


class OpenAILLMProvider(LLMProvider):
    """Real LLM provider backed by the OpenAI chat-completions API.

    Configuration comes from the existing `Settings.llm_*` fields. The
    `openai` package is imported lazily so the rest of the framework and
    the offline test suite never need it installed.
    """

    name = "openai"
    generation_mode = "llm"

    def __init__(self, settings_=None):
        from app.config import settings as _singleton

        cfg = settings_ if settings_ is not None else _singleton
        if cfg.is_mock_llm or cfg.llm_provider != "openai":
            raise LLMConfigurationError(
                "OpenAILLMProvider requires LLM_PROVIDER=openai and LLM_API_KEY set"
            )
        self.model = cfg.llm_model or "gpt-4o-mini"
        self._api_key = cfg.llm_api_key
        self._client = None

    def _client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise LLMUnavailableError(
                    "The 'openai' package is not installed; run "
                    "`pip install openai` to use a real LLM."
                ) from exc
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client().chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception as exc:
            raise LLMUnavailableError(
                f"OpenAI LLM call failed using model '{self.model}': {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_provider(settings_=None) -> LLMProvider:
    """Build the configured provider, honoring the existing no-key fallback.

    Convention (see `app/config.py Settings.is_mock_llm` and `app/main.py`):
    if the provider is 'mock' OR no API key is set, MOCK mode is used so the
    application never breaks without a key.
    """
    from app.config import settings as _singleton

    cfg = settings_ if settings_ is not None else _singleton

    if cfg.is_mock_llm:
        return MockLLMProvider(settings_=cfg)

    if cfg.llm_provider == "openai":
        return OpenAILLMProvider(settings_=cfg)
    if cfg.llm_provider == "anthropic":
        raise LLMConfigurationError(
            "LLM provider 'anthropic' is not implemented in Phase 7; "
            "use LLM_PROVIDER=openai (with LLM_API_KEY) or leave it mock."
        )
    raise LLMConfigurationError(
        f"Unknown LLM provider '{cfg.llm_provider}'. "
        "Expected one of: mock, openai, anthropic."
    )