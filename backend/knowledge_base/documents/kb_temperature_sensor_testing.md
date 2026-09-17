# Temperature Sensor Testing

## Overview

A temperature sensor must be tested both for the values it reads and for how
it reports them over the communication channel. The two most important
aspects are the measurement range and the accuracy of the reading.

## Range testing

The requirement typically declares a measurement range such as -40 Celsius to
125 Celsius. Verify the device reports valid measurements inside the range and
that it exposes a defined, error-free behaviour exactly at the minimum and
maximum values. Test temperatures below the minimum and above the maximum to
confirm out-of-range handling (clamping, an error flag, or no bogus value).

## Accuracy testing

Accuracy requirements such as plus or minus 0.5 Celsius state how close the
reported value must be to the true temperature. Compare device readings
against a calibrated reference at several points across the range, including
the middle of the range and both extremes.

## Behavioural checks

- Set-point and hold: the reported value must reflect the applied temperature.
- Latency: the delay between a temperature change and the reported reading.
- Sample-to-sample stability: repeated readings of a constant input should not
  jump beyond the accuracy tolerance.
- Cold start and warm-up behaviour near the range boundaries.