# Negative Testing

## Overview

Negative testing verifies that a device behaves safely and predictably when it
is given invalid input, when the environment is hostile, or when subsystems
fail. The goal is to confirm the device fails gracefully instead of crashing
or emitting nonsense data.

## Typical negative scenarios

- Out-of-range values: temperatures or other measurements above the maximum
  or below the minimum of the declared range.
- Malformed input: truncated, empty, or wrongly-typed payloads sent to the
  device's communication channel.
- Wrong protocol messages: bytes on the topic that are not valid MQTT/JSON.
- Missing data: an expected sample or message that never arrives.
- Sensor faults: a sensor returning NaN, a shorted line, or no value at all.
- Resource exhaustion and power interruption during a send.

## Pass criteria

A negative test passes when the device detects the invalid condition and
either rejects it, flags it, or recovers, and never produces fabricated or
garbage values. The requirement defines what the correct reaction is; the test
must assert that reaction, not just that the device "did not crash".