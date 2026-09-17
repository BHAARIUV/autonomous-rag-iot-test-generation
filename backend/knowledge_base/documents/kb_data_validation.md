# Data Validation

## Overview

Data validation tests verify that every value entering or leaving the device
is checked against the contract in the requirement: type, range, units,
format and completeness. Invalid data must be rejected or flagged, never
silently accepted or mislabelled.

## What to validate

- Type: the field must have the declared type (number versus string).
- Range: numeric fields must respect their minimum and maximum.
- Units: values must carry and convert the declared unit correctly; mixing
  Celsius and Fahrenheit, or milliseconds and seconds, is a classic fault.
- Precision and format: decimals must be rounded or truncated to the contract,
  timestamps must use the agreed encoding, enumerations must come from the
  declared set.
- Completeness: required fields must be present and non-empty.

## Validation behaviour to test

- Rejection with a clear, machine-readable error for invalid messages.
- Default/fallback behaviour when an optional value is missing.
- That invalid values never leak into downstream consumers.
- That borderline values exactly at a limit are accepted or rejected exactly
  as the requirement specifies, matching boundary value analysis.