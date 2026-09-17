# Device Offline and Recovery Testing

## Overview

IoT devices are frequently offline: batteries die, networks disappear, and
brokers go down. Offline/recovery testing verifies the device can buffer or
handle data while disconnected and return to normal operation cleanly when
connectivity returns.

## Offline behaviour to test

- Graceful degradation: the device must keep sensing locally and must not
  crash or fill memory while the network is unavailable.
- Buffering: if the device queues messages while offline, verify the queue
  bounds, the oldest/newest retention policy, and what happens when the buffer
  is full.
- Status reporting: the device should expose an offline/online status that
  subscribers can observe.

## Recovery behaviour to test

- Reconnection: the device must reconnect using its retry/backoff policy and
  resume publishing.
- Backlog flush: queued messages are sent after reconnect, in the defined
  order and with correct timestamps, without flooding the broker.
- State consistency: local state read while offline must be consistent with
  what the device reports once back online.
- Battery edge cases: a low-battery device offline must still perform its
  recovery handshake once power and network return.

Recovery tests should assert the exact recovery contract in the requirement,
not merely that the process eventually resumes.