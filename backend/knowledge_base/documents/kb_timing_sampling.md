# Timing and Sampling Tests

## Overview

Timing and sampling tests verify that a device measures and reports data at
the rate and with the latency its requirements specify. Sample intervals,
publication rates and transmission delays are all timing contracts that must
be asserted against real clocks.

## Sampling interval tests

If a requirement states a sampling interval (for example one sample per
second), measure the elapsed time between consecutive samples. Verify:

- The mean interval matches the requirement within an acceptable tolerance.
- No interval is wildly short or long (jitter).
- The interval starts immediately after power-up / restart.

## Publication latency tests

Measure the delay between a physical event (a temperature change) and the
message that reports it appearing on the output topic. The requirement may
bound this latency explicitly.

## Clock and scheduling concerns

Firmware scheduling can stretch intervals under load, so timing tests should
run with the device under its typical load. Tests must use an external,
trusted clock rather than the device's own timer when verifying absolute
latency, and should tolerate a defined amount of jitter while failing on
consistent drift.