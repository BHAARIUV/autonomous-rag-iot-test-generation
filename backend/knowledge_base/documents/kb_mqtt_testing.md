# MQTT Testing

## Overview

MQTT is the lightweight messaging protocol used for communication between the
device and the broker. The device communicates by publishing telemetry to
topics and by subscribing to topics for commands, all over MQTT. MQTT
reliability is governed by QoS levels, retained messages and reconnection
behaviour. Testing MQTT behaviour therefore requires verifying that the device
communicates according to the protocol contract.

## What to test

- Publish frequency and payload format: each message must match the expected
  JSON schema on the configured topic.
- Topic correctness: messages must go to the exact topic name in the
  requirement (for example iot/sensor/temperature), never a typo.
- QoS contract: QoS 0 at-most-once, QoS 1 at-least-once with acknowledgement,
  and QoS 2 exactly-once delivery semantics.
- Retained messages: after a device failure, a newly read value must be
  published so subscribers receive fresh data.
- Clean session / persistent session behaviour across reconnect.
- Broker failures: when the broker is unavailable, the device must retry and
  re-establish the connection without crashing.

## Subscription testing

Subscribers must handle missing a message when QoS is not guaranteed, handle
duplicated messages when QoS 1 is used, and filter by topic correctly. Test
that a subscriber receives every published message in order for the topics it
subscribed to.