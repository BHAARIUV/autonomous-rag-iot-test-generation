# Sensor Accuracy Testing

## Overview

Sensor accuracy testing verifies how close a device's reported value is to the
true value of the measured quantity. Accuracy is typically expressed as a
tolerance (for example plus or minus 0.5 Celsius) around the true value and is
a per-requirement contract, not a device property to guess.

## Method

- Use a calibrated reference instrument better than the tolerance under test.
- Stabilise the sensor at the test temperature before recording a reading.
- Sample across the full measurement range: low end, middle, high end, and
  both boundaries.
- Record the error (reported minus true) for each point and compare with the
  accuracy requirement.

## What to report

- Accuracy error at each test point in the same unit as the requirement.
- Maximum absolute error seen anywhere in the range.
- Repeatability: the spread of repeated readings at the same input.
- Drift: change in reading over time and across warm-up.

Accuracy tests only pass when the measured error is within the declared
tolerance at every required point; outside-tolerance results are defects linked
to the accuracy requirement.