# Repeated sealed continuation after a terminated attempt

The two current native024 attempts continue with their original source and
7,200-second caps. `resume_chained_sealed_stream.py` is a separate driver for
a later attempt only if an existing sparse-resume attempt actually fails or
times out. No actual cut has been prepared and no native session has been
started with this driver.

The earlier sparse driver did not recognize its own receipt schema as a
possible source. In addition, an unfinished heartbeat contains this attempt's
reconstruction cost, while its inherited reconstruction cost remains in the
bound ancestor cut. Reusing that heartbeat without the ancestor would omit
previous reconstruction work.

The new driver accepts the old sparse receipt and its own receipt, binds the
ancestor cut and the complete binary/suite/horizon/event-budget command, and
adds inherited reconstruction cost to the current reconstruction exactly once.
Controller, export and seal costs already accumulate in the heartbeat and are
not added again. Unsealed excluded-tail costs remain charged, while any
unpublished work remains unknown.

Independent review identified two further defects before execution. A timeout
before the first new checkpoint has `latest_native_seal=null`; the adapter now
selects the hash-bound ancestor seal using a local heartbeat copy. The original
heartbeat is untouched and the original raw shard must still contain that exact
seal. Process absence now binds the complete source worker command and parent
command, positive PID, creation time, parent-child relationship and a hash-bound
earlier CIM observation. Matching an output directory alone is insufficient.

The original known-seal replay still precedes access to a native session or
controller state. Input, FIFO, physical graph, inventory, policy and native024
binary remain unchanged. The adapters operate only within the new serial
process and restore original functions even after an exception. A known
timeout is recorded as a terminated attempt, not as a new user pause.

Validation: 28 pure tests passed in `chained_sealed_resume_pure_002.xml`, and an
independent source review confirmed both corrections. These tests establish
the preparation and rejection rules only. An actual continuation remains
conditional on a future terminated attempt, exact process-absence evidence and
successful full-tape reconstruction against that attempt's known native seal.

The four currently running parent/worker identities were read through CIM and
saved in `user_resume_20261015_001/active_process_identity_004.json`; all four
complete commands match their source receipts. This is a live identity record,
not evidence that any process has exited.
