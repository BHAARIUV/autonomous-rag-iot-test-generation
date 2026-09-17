# Boundary Value Analysis

## Overview

Boundary Value Analysis (BVA) is a black-box test design technique that
focuses on the edges of input domains. Most software and firmware defects are
found at boundaries because comparison operators (less than, greater than,
equal) tend to make off-by-one errors there.

## Method

For any input domain with a declared minimum and maximum, derive test values
at the boundary values themselves and immediately on either side. For a range
-40 Celsius to 125 Celsius, the boundary values to test are:

- below minimum: -41 Celsius (invalid / out-of-range side)
- the minimum itself: -40 Celsius (valid boundary)
- just above minimum: -39 Celsius (valid)
- the maximum itself: 125 Celsius (valid boundary)
- just below maximum: 124 Celsius (valid)
- above maximum: 126 Celsius (invalid / out-of-range side)

## Why it matters for IoT

Sensor ranges, sampling intervals and timing windows are all numeric domains
with boundaries. A requirement that says the range is -40 C to 125 C is most
likely to be violated exactly at those two values, so boundary tests must map
back to the specific requirement under test.