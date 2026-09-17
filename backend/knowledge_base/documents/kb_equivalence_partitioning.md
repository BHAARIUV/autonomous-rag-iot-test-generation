# Equivalence Partitioning

## Overview

Equivalence Partitioning (EP) divides an input domain into classes of values
that the device is expected to treat identically. Testing one representative
value from each class gives good coverage with few test cases.

## Method

Split valid and invalid inputs into equivalence classes. For a temperature
range of -40 Celsius to 125 Celsius, a typical partition set is:

- Valid class inside the range, e.g. 20 Celsius.
- Invalid class below the minimum, e.g. -60 Celsius.
- Invalid class above the maximum, e.g. 200 Celsius.

Within each class the device behaviour should be the same, so one value per
class is enough to accept or reject the partition.

## Combining with boundary analysis

Equivalence partitioning finds whole classes; boundary value analysis then
tests the exact edges of those classes. The two techniques are complementary
and are usually applied together on the same requirement. Every chosen
representative value must still be traceable to the requirement it verifies.