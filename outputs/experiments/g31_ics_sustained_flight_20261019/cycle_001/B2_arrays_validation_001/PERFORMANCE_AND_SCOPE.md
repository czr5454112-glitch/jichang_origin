# B2 independent per-call array predictor

The new interface preserves the frozen B1 mathematical model and public-data contract. The original B1 forecaster, original public audit, and native collection sources were not changed. This is a computation optimization; it supplies no execution authority, action outcome labels, policy benefit evidence, or native latency certification.

The previous 946-row audit stopped after 202 rows at its unchanged 240-second soft budget. A registered one-row profile found B1 prediction consumed 1139.6393 of 1203.1165 milliseconds of plain pipeline wall time. The profile attributed most prediction cost to repeated NumPy conversion of region CDF lists inside the sequential flight loop. Profiled durations include instrumentation overhead and are not a benchmark.

`foundation_flight_forecaster_arrays.predict` performs the original full validation on every call, converts the fixed window grid once per call and each validated region's CDF edges/values once per region, and retains the original flight accumulation order. There is no cross-call model, observation, prediction, or evidence cache. No dynamic source freshness check is relaxed.

The bounded `B2_arrays_validation_001` run passed:

- All 402 saved complete B1 forecasts are byte-exact: 134 prior-only, 134 original synthetic as-of count, and 134 unchanged recent-rate outputs. All numerical fields, uncertainty, masks, metadata, and digests are compared.
- Three actual B2 observations, sequences 0, 473, and 945, were recomputed with both implementations. Complete forecast, public projection, wrapped observation, candidate semantics, and all action features are byte-exact.
- AST comparison confirms the predictor function differs only in per-call array materialization and original helper qualification.
- Runtime and input bytes were pinned; no fitting or native run occurred. The offline validator reconstructed only the original explicitly synthetic as-of count feeds. The optimized runtime reads no private index or labels.
- Nineteen small synthetic tests preserve original refusals, missing data, input immutability, valid changed model/plan behavior, and complete output bytes.

| Actual B2 sequence | Original prediction wall ms | Array prediction wall ms | Original thread CPU ms | Array thread CPU ms |
| --- | ---: | ---: | ---: | ---: |
| 0 | 1231.4156 | 116.6991 | 1171.875 | 125.0000 |
| 473 | 1176.4391 | 104.0469 | 1125.0000 | 109.3750 |
| 945 | 1085.5293 | 93.1825 | 1046.8750 | 93.7500 |

These are three sequential offline prediction pairs. Wall and current-thread CPU clocks are separate; Windows CPU quantization can exceed a short wall sample. They are not randomized performance samples or the complete collection→guard→submit path, and they do not establish a 100-millisecond native controller guarantee. Ordinary background system load was uncontrolled. Validation outer time reported by the parent was 37.203 seconds.

The new `foundation_airport_learning_audit_arrays` runner uses the original 240-second soft / 270-second hard budget for all 946 historical public callback records, with native=0, fit=0, outcome labels=0. It requires the completed validation receipt and matching predictor/model/context/trace/mapping bytes before preparation and run. Its entire replay loop is AST-identical to the original except the predictor import and explicit use of the original checkpoint validator. Public projection, observation validation, missing/unknown handling, feature construction, and rejection behavior are unchanged. Thirty-four pure tests passed.

The parent subsequently registered and executed `B2_public_feature_audit_arrays_001`: it completed all 946 records with 946 successful B1 forward calls, zero rejected records, 463 proposal feature vectors, and 296 records containing current free inventory. Inner audit wall time was 193.688 seconds; parent outer time was 196.312 seconds. The full original budget now suffices, whereas the preserved original audit stopped after 202 records. This does not establish a randomized speed ratio or a 100-millisecond controller path. Aggregate audit time includes data decoding, validation, projection, feature construction, hashing, and writing.

An independent stdlib-only audit recounted all 946 saved rows and all 463 finite 88-feature vectors, checked source/input/output hashes, and verified every target/outcome label is null and every proposal's enabled status remains unknown. All account unknown flags and original forecast cutoffs are preserved. The 202 previously saved original-audit rows match the new first 202 serialized JSON lines exactly. Actual callback counts are domestic 567 and international 379; residual callbacks make these counts unequal. An initial reviewer-only equal-count assertion was corrected to the original recorded owner set; no producer data or source was altered. This independent saved-output audit used no forward pass, training, or native execution. It establishes public feature compatibility, not actual action execution, training readiness, or control benefit. Evidence is `../B2_public_feature_audit_arrays_001/independent_complete_rows_audit_001.json`.

Evidence: `receipt.json`, `plan.json`, `../B2_public_profile_001/receipt.json`, `../B2_public_feature_audit_arrays_001/plan.json`, and `../B2_public_feature_audit_arrays_001_task.json`.

Frozen SHA-256:

- Array interface: `401a283b890da04408b45e1a9cc7ac4a2db0b579ac95c418b9a263611d55cf64`
- Validation receipt: `f6050660c6dc862ceb65efd76e6850a3f411955d8601c55e95e8ad8e0b04a6a5`
- New full-audit source: `8539bbb3ee1dd207b7612ebe13424f5760b031f9fb05da74b36f0737d30f36e7`
- Prepared full-audit task: `c174e5e7001d9a29ed03c89bfe08f89120684efaa979e70db9a48d640c1785ed`
