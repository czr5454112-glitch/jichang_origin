# G4IRSF22 congestion episode evidence

Status: `DETECTION_COMPLETE`.

These are **route-decision-sampled** congestion episodes, not continuous queue telemetry. Start, peak, and end denote sampled Route decisions.

## Signal and hysteresis

- Signal: `max(candidate-consistent current junction_queue_length, candidate-consistent current priority_local_contention)`.
- Enter/exit: `16` / `8`.
- Rationale: enter at at least 16 local queued/contending bags and exit at at most 8; the two-to-one band suppresses decision-sample jitter.
- Candidate target queues and any future/global information are excluded.
- Census rows: `464,849`; candidate-current consistency: `PASS`.
- Signal p50/p90/p95/p99/max: `12.000` / `32.000` / `32.000` / `32.000` / `32.000`.

## Coverage

- Episodes: `339` (`339` closed, `0` open at census end).
- Owners: `12` — `6, 9, 11, 16, 19, 20, 22, 27, 31, 36, 38, 52`.
- Time blocks: `19` — `4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22`.
- Legs: `3` — `direct, storage_in, storage_out`.

Each descriptor retains owner, start/peak/end, time block, leg coverage, queue slope, and a bounded sample of affected Route rows. `affected_row_count` always records the full sampled count.
Affected rows are sampled decisions, not independent bags. A closed sampled episode does not prove that a continuously observed physical queue emptied, and the 16/8 episodes are descriptive rather than independent causal units.
