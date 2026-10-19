# Independent 500k calibration hard-timeout audit

This attempt is incomplete. The process reached its 300.015-second hard limit, and no native acceptance, worker report or final raw artifact exists. Process exit code zero does not change that conclusion.

The last saved complete snapshot is at physical time 43200: full population 28,506, observed 14,464, loaded 247, business-completed 241, cumulative events 181,864. Its tray modes are six loaded, three empty transfers, 12 empty and one quarantined. Exact stop time is unknown; 786 complete public callback records prove progress to at least 46500. Do not report the 43200 snapshot as the final state or infer that motion stopped there.

Node49 receiving admission remains effective through the saved snapshot: remote leases never exceed three, counted occupancy never exceeds four, and all 121 replayed grants subtract their own reservation and require occupancy below three. The previous seven completed jobs retain equal completion times; the other 28,499 job comparisons are incomplete/unknown. All incomplete and unreleased jobs remain in the denominator.

The full 121,415,394-byte original callback artifact remains unchanged. It expands to 2,344,203,978 bytes; its last row contains 4,796 ledger entries twice. The recorder repeatedly serialized these and the recurring context fields. Soft240 was only checked before each 3600-second segment, so the segment entered at wall162.64 could continue through hard300 without a partial closure check. Timestamps continue advancing; there is no evidence here of a same-time native spin.

The last callback at46500 contains six supplies and six baseline intents. No late observation exists after57660 and successful common warmup is unproven, so C10 eligibility is unknown and no C10 should be prepared from this run.

`audit_hard_timeout.py` generated `report.json` using only the standard library, without native, controller, model or `result_at` execution. The JSON report binds archived hashes and contains the exact per-segment evidence. The separate lossless recorder/soft-boundary follow-up is documented in `docs/g31_ics_circulation/AIRPORT_RECORDING_AND_SOFT_BOUNDARY_20261019.md`; it does not alter or relabel this failed attempt.
