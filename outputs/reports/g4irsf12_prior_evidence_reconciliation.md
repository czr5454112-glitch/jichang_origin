# G4IRSF12-A Prior Evidence Reconciliation

Date: 2026-07-23

## Authoritative G4IRSF11 facts

| Fact | Reconciled value | Primary evidence |
| --- | ---: | --- |
| Formal cases executed | 84 / 84 | `artifacts/gates/g4irsf11_event_runtime_completion.json` |
| Formal gate distribution | 3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER | `outputs/tables/g4irsf11_event_runtime_gate.csv` |
| Complete raw bags | **3,114 / 28,506** | `outputs/tables/g4irsf11_event_runtime_case_ledger.csv`; 28,506 - 25,392 end backlog |
| Completed segments | **12,125 / 43,603** | `outputs/tables/g4irsf11_event_runtime_case_ledger.csv` |
| Failed segments | 31,478 | same ledger row |
| Deadline miss rate | 97.30% | same ledger row |
| Starved raw bags | 28,460 | same ledger row |
| Deadlock episodes / unresolved | 41,739 / 4 | same ledger row |
| Conflicts / runtime full A* / global scans | 0 / 0 / 0 | same ledger row |
| Original-entry p95 / p99 | 37.89 h / 40.28 h | same ledger row |
| Maximum wait | 76.13 h | same ledger row |
| Maximum junction utilization | 16.17% | same ledger row |

The completed-segment value is **12,125**, not 2,125.  Cohort status
`COMPLETE` means all predeclared evidence cases executed; it does not mean the
algorithm passed.  The six final runtime gates contain three PASS rows and
three explicit blockers.

## Historical baseline denominators

| Stack/evidence | Denominator | Mean minutes | Completion | Claim boundary |
| --- | --- | ---: | ---: | --- |
| Original-project IoT-DRPA/HCA* text | `processed_segment_attempt_time_tth` | 3.967122711 | 28,506 / 28,506 | parsed historical output; not a fresh Java rerun |
| Same historical output, recomputed | `java_release_time_tth` | 5.197225146 | 28,506 / 28,506 | recomputation only |
| Same historical output, recomputed | `original_entry_time_tth` | 5.764936746 | 28,506 / 28,506 | recomputation only |
| Frozen v2-safe | `java_release_time_tth` | 3.556593853 | 28,506 / 28,506 | old central replay/future-reservation skeleton |
| Frozen v2-safe | `original_entry_time_tth` | 4.124305453 | 28,506 / 28,506 | same v2-safe result recomputed |
| G4IRSF11 event runtime | any survivor-only denominator | not comparable | 3,114 / 28,506 | incomplete; excluded from latency victory claims |

Therefore `3.967122711` must not be used as an
`original_entry_time_tth` target.  A future original-entry comparison must use
a matched original-entry baseline and must also display Java-release and
processed-attempt values.  All historical HCA* rows remain parsed evidence,
not a same-machine executable rerun.

## Reconciled evidence boundaries

1. `outputs/reports/g4irsf11_fixed_real_map_runtime_decision_brief.md` is the
   concise handoff, while the completion JSON and case ledger are the primary
   machine-readable values.
2. `outputs/reports/g4irsf11_gate_integrity_audit.md` is a different, earlier
   Gate-A audit of checked-in G4IRSF10 evidence.  Its overall `FAIL` must not be
   confused with the final six-row runtime gate distribution above.
3. The ledger `input_sha256` value `258b6e05d4502b32f9e26749b6196a4ba5ea306f206d1269592bc2648ea65a24` is the
   derived paper-full workload hash.  The protected source-file hash remains
   `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`.
4. `outputs/tables/g4irsf11_source_identity_audit.csv` covers the bounded combined trace source
   (`.pytest_cache/g4irsf11/event_evaluation/traces/g4irsf11_trace_tasks_combined.jsonl`, 3,072 segments and
   26,692 decisions), not all 43,603 source
   rows.  Its report sentence claiming complete-input coverage must not be used
   as full-source evidence; the direct file hash/row/unique-task audit in this
   phase is authoritative.
5. Frozen v2-safe is a valid control but not the same architecture: it retains
   a central task-to-goal loop and future node reservations.  Its `PIBT-lite`
   label is same-bag alternative scanning, not recursive multi-bag PIBT.

## Reusable validators

- `scripts/eval/g4irsf11_fixed_map.py`: fail-closed map identity and dimensions;
- `scripts/eval/run_g4irsf11_event_runtime_evaluation.py`: source raw/semantic identity and cohort publication;
- `scripts/eval/validate_g4irsf11_committed_artifacts.py`: committed artifact hash and semantic validation;
- `scripts/eval/g4irsf11_g4irsf10_audit.py`: frozen v2-safe scale evidence boundary;
- `scripts/eval/run_g4irsf8_source_release_denominator_validation.py`: denominator reconstruction (generator; do not run during a read-only audit);
- `scripts/eval/g4irsf12_phase_a.py`: this phase's read-only check and small-report publisher.
