# LT2 C3: activation-local observation reuse

Date: 2026-10-14. This is a semantics-preserving Python implementation improvement, not a new routing method or a complete-request 100 ms certificate.

## Measured negative: copying a public cache

The saved native016 original24 immutable request sequence was replayed at exactly its recorded submission times. Every returned submission reply and the final jobs, trays, transfers, receipts and leg identities matched the saved execution. At physical times 20,000, 60,000 and 86,400 seconds, both owners were measured with 30 serial samples per operation.

A proposed cache using one fresh native observation plus two deep copies was **5.69–8.15 times** as costly as two fresh native observations across these six owner/time samples. That public-cache design was not installed. Complete samples and source/run identities are retained in [c3_observation_micro_001/receipt.json](../../outputs/experiments/g31_ics_lt2_20261014/c3_observation_micro_001/receipt.json); the replay driver is [c3_observation_micro_driver.py](../../outputs/experiments/g31_ics_lt2_20261014/c3_observation_micro_driver.py).

## Implemented scope and invariants

`_activate_owner` obtains the same compact service observation as before and passes it read-only to `_publish_services`. It can reuse that local object for the first `transfer_candidates` call only when all of these conditions hold:

- Prebalancing uses the same compact projection.
- No submission occurred after acquiring the snapshot; even a rejected submission invalidates reuse because client state can change.
- The two consumers remain within this one owner activation, before another native drain.

Retries and demand publication occur before the snapshot is acquired. A subsequent transfer submission still forces a fresh residual observation, as before. `_publish_services` and `transfer_candidates` do not mutate the supplied snapshot. There is no public cache: separate `ProtocolClient.view` calls still return isolated nested data. The runtime diagnostic switch `_reuse_service_observation=False` restores fresh reads and is excluded from policy configuration and checkpoint state.

Implementation: [event_protocol_control.py](../../scripts/experiments/g31_ics_circulation/event_protocol_control.py), [protocol_control.py](../../scripts/experiments/g31_ics_circulation/protocol_control.py). Tests: [test_g31_circulation_observation_reuse.py](../../tests/test_g31_circulation_observation_reuse.py).

## Actual original24 comparison

One serial pair used the saved input and configuration from `request_profile_original24_002`, the existing native016 binary SHA256 `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`, and the same complete H=86,400 observation horizon. Neither branch used cProfile. The wrapper measured native observation calls in both branches.

| Measure | Fresh observations | Internal reuse |
|---|---:|---:|
| Complete controller-call wall time | 87.707162 s | 50.744693 s |
| Owner activations | 8,934 | 8,934 |
| Native observation calls | 17,891 | 10,005 |
| Native observation wall time | 54.601611 s | 27.687096 s |
| Reused internal snapshots | 0 | 7,886 |

The observed wall reduction was 42.14% in this pair. This is a diagnostic measurement on one host, not a statistically established speedup across machines or a guarantee for every workload. Both final native hashes were `e23c986383c443547a78803006e1c17e73d453cf8931f6d2b2eda11b5b5ffee5`.

Independent saved-output verification established exact equality for public requests including retries, owner decisions and activation causes, native batch boundaries, JSON controller state, and jobs/trays/transfers/receipts/leg identities. Those fields also match the earlier saved original24 run, after excluding measurement-only fields. Native final hashes agree between the two new branches. Original measurement samples and runs were retained. [Independent verification](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/independent_validation.json), [actual progress measurements](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/progress.json), [fresh run](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/fresh.json.gz), [reuse run](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/reuse.json.gz).

The original benchmark worker exited 1 **after saving both actual runs**: its reporting code used `pop('owners')` on the loaded original configuration before comparing that reference. This was a harness mutation, not a different native configuration. Its failed [receipt](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/receipt.json), [stderr](../../outputs/experiments/g31_ics_lt2_20261014/c3_internal_reuse_pair_001/stderr.log), and archived original driver remain unchanged. The separate [read-only verifier](../../outputs/experiments/g31_ics_lt2_20261014/c3_reuse_verify_saved.py) reread the three saved runs without mutation and passed all equality checks. The reusable [comparison driver](../../outputs/experiments/g31_ics_lt2_20261014/c3_reuse_pair_driver.py) now copies that configuration before removing its separate owners argument; this reporting fix did not require repeating the native executions.

## Validation and remaining work

The final focused suite passed **76 tests** on native016, including 12 observation-reuse cases and the existing lifecycle, protocol, event-controller and owner-notification regressions. Coverage includes full versus compact projection, ACK loss, duplicate delivery, owner outage, rejected submission invalidation, nested mutation isolation, JSON resume with the runtime reuse flag changed, one-event/one-activation budget continuation, and strict zero-delay/adjacent-float boundaries. [JUnit](../../outputs/experiments/g31_ics_lt2_20261014/c3_reuse_regression_002.xml).

This observation-reuse experiment introduced no active-outbox index, history deletion or native projection change. A later LT2 change adds a derived active-request/cooldown index while retaining all history. Its full1x prefix passed exact semantic comparison but showed no measured speedup (13.524 s full scan, 13.538 s indexed). See [the current LT2 record](LT2_PROGRESS_20261014.md) and [its source-bound receipt](../../outputs/experiments/g31_ics_lt2_20261014/c3_active_request_index_full1x_prefix_001/receipt.json). Native history serialization and repeated candidate/path construction remain separate targets. Neither result closes normal-service protection, full original-flow business success, method novelty, or complete-request <=100 ms gates.
