# Communication Reliability

## Overview

Communication reliability tests verify that a device keeps exchanging data
correctly under realistic network conditions: dropped packets, broker
restarts, reconnects, and message duplication. The goal is that data is
delivered with the semantics the protocol and the requirement promise, even
when the network degrades.

## Test scenarios

- Dropped packets: with QoS 1 or QoS 2, an acknowledged message must survive
  a dropped delivery attempt.
- Broker restart: the device must reconnect and resume publishing after the
  broker (or network) returns.
- Reconnect storm: many rapid disconnects and reconnects must not leak
  connections or corrupt state.
- Message ordering: for a given topic, messages should arrive in publish order
  for the QoS/topic combination used.
- Duplicates: with QoS 1, duplicates may occur; consumers must handle them
  idempotently. Exactly-once (QoS 2) must not create duplicates.
- Gap handling: periods of no connectivity must not crash the device; newly
  available readings must be published after recovery.

## Pass criteria

Measurements of delivery rate, retry counts and reconnect time should be
recorded against the requirement's expectations, and the device state after
each disruption must match the recovery contract in the requirement.