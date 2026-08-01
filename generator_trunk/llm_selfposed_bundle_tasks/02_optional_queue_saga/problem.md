# Scenario 02_optional_queue_saga — optional sudden actions

**Category:** optional sudden actions (pattern like `generator_trunk/usecases/event_order`).

## Simple-language user problem
"My message-queue consumer does fetch -> process -> ack. I also worry about a redelivery (the same message arriving twice) and a crash before ack. Which orderings and which fault combinations break correctness?"

## What Bundle can offer
Bundle runs the consumer steps in every order and bolts on two optional 'sudden actions' (redelivery, crash-before-ack) as a separate dimension, then a saga oracle checks ordering, idempotency, and liveness across all combinations.

## Hypothesis
Only fetch<process<ack is valid; a redelivery without an idempotency key double-processes; a crash before ack loses liveness.

## Freedoms -> ZEN verbs
- **consumer step order** -> shape *an ordering* -> `FW_Permut` (3! = 6).
- **redelivery may or may not fire** -> shape *may-or-may-not (sudden action)* -> `FW_Optional` (x2).
- **crash-before-ack may or may not fire** -> shape *may-or-may-not (sudden action)* -> `FW_Optional` (x2).

## Oracle (meaning)
FW_VAR=3 process before fetch; 2 ack before process; 4 double-process; 5 not-acked without crash cause; 0 PASS

**Goals:** `process_count:min`.
