# IoT Testing Fundamentals

## Overview

IoT systems combine embedded firmware, sensors, wireless or wired connectivity,
cloud backends and end-user applications. Testing a complete IoT device means
verifying each layer and the integration between layers, not just the sensor
reading.

## Test layers

A device test plan typically covers hardware operation, firmware behaviour,
sensor accuracy, data transmission formats, communication protocols such as
MQTT, and cloud-side data handling. Tests should exercise the device in the
field-like conditions it will actually run in.

## Good practices

- Test both normal operation and abnormal conditions: power loss, network
  gaps, sensor faults, and invalid input values.
- Keep tests deterministic and repeatable: the same stimulus must produce the
  same observation.
- Record the environment, the inputs, and the expected result for every test.
- Link every test to a requirement so coverage can be measured.
- Prefer automated execution so regressions are caught as firmware changes.

## Common pitfalls

Testing only the happy path is the most common gap. Devices fail when values
are out of range, packets are dropped, or the network is temporarily
unavailable, so those scenarios must be tested explicitly and linked to the
requirement they verify.