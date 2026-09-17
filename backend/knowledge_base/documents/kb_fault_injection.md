# Fault Injection

## Overview

Fault injection deliberately forces failures — on the sensor, on the
communication link, or in firmware — so the team can verify the device reacts
according to its requirements. It is the standard way to test reliability and
safety requirements that normal testing never triggers.

## What to inject

- Sensor faults: readings outside range, NaN, constant values, or a sensor
  line that stops responding.
- Communication faults: dropped MQTT messages, topic misdirection, broker
  outage, delayed or reordered packets.
- Hardware faults: simulated power loss, restarts, and stuck peripherals.
- Firmware faults: exception handlers, watchdog timeouts, and resource
  exhaustion.

## How to verify a fault injection test

Each injected fault must produce the observable behaviour the requirement
declares: a specific error code, a fallback value, a reconnection, or a safe
state. The test records the fault, the observed behaviour, and whether the
device recovered. Requirements such as high-severity safety/overheat rules are
the primary candidates for fault injection coverage.