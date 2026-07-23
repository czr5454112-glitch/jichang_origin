# G4IRSF12 Buffer Semantics Boundary

Status: `PHYSICAL_BUFFER_CAPACITY_NOT_ESTABLISHED`.

The fixed map contains node type, service time, coordinates and directed outgoing edges. It does not declare a queue/buffer capacity per node.

The current event runtime default at `cpp/ics_core/runtime/event_driven_junction.hpp:116` uses `local_queue_capacity = 0`, explicitly meaning no configured cap. Therefore a conflict-free run under that setting is not evidence that a physical waiting location can hold the observed queue.

The reviewed Java task generator at `legacy/jichang_origin_readonly/src/App/Tasks.java:151` gates new work when a start already has an unfinished task. This is an observed source-generation rule, not an authoritative capacity for every source, merge, diverter, EBS, or destination buffer.

## Required boundary for later A/B

- Keep unknown capacities explicit; do not substitute a convenient finite value.
- Report source queue, admitted network queue, scheduled incoming, and service calendar occupancy separately.
- Treat `capacity=0` as unbounded configuration, never zero physical spaces.
- Bind any finite capacity to an authoritative project source and a source hash.
- Until then, R2/R4 headway and buffer values are sensitivity-only and cannot support a physical-capacity or throughput-optimality claim.
