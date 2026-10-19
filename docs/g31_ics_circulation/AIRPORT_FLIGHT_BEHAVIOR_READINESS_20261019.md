# Airport flight-conditioned behavior learning: evidence and fixed next gate

This stage connects the frozen B1 flight forecaster to real airport public
observations and now trains a real action-conditioned airport behavior model
on executed-action evidence. It has not demonstrated control benefit or
established airport RL.
The 28,506 physical jobs, 151 nodes, 22 trays and full airport clock are retained.

## Executed public-input audit

`cycle_001/B2_public_feature_audit_002` made **202 actual B1 forward calls** and
validated **202 callback records / 99 proposal feature vectors**, with zero
input rejections, before its 240-second soft budget expired (241.0 seconds).
The full registered population was 946 callback records: **the full replay did
not pass**. Its original receipt and partial feature file are preserved. No
training, native invocation, label generation, or model-selection occurred.

The separately registered `B2_public_feature_audit_arrays_001` subsequently
completed all **946 callbacks / 946 actual B1 forwards / 463 vectors of 88
features**, with zero input failures or labels. Its 193.688-second inner run
and independent saved-output recount are closed. All 202 earlier serialized
rows match exactly. The per-call array conversion preserves the original
forecaster's output bytes; this is a public-input compatibility result, not
evidence that proposed actions executed or improved control.

The adapter uses actual public waiting-group counts rather than counting the
representative jobs. Missing counts remain unknown. All waiting completeness
masks are false: a matching schema and an absent local group do not themselves
attest a complete native FIFO scope. Exact group count and observation time
are still retained. Inbound and outbound coverage remain incomplete because
the callback does not carry sufficient receiver-public transfer payload/ACK
or original submission generation. Sender-owned requests do not mint receiver
inventory. Active own claims conservatively remove the same physical tray
from reusable supply.

The native binding exposes unloading `available_at` as `UNLOAD_START +
unload_seconds`; the runtime changes it to `unload_complete + hold_seconds`
when entering hold. Consequently the adapter adds hold once for an unloading
tray and never again for a hold tray. This is a conditional estimate of local
operation duration, not a congestion upper bound or actual free inventory.
The native source locations are `circulation_session_binding.hpp:225–226` and
`circulation_runtime_impl.hpp:746–752`. Twenty public-adapter tests passed.

The frozen forecaster remains prior-only in the main airport path:
`observed_counts=None`. Actual callback job metadata lacks a legal public
STD/flight-parent association. No private crosswalk fills that gap. The static
plan remains a retrospective experimental predeclaration, not proof of real
publication/receipt history. Nodes outside its public region mapping carry
unknown demand, not structural zeros. Forecast outputs are observations for
the action model; they are never action-outcome labels.

## Fixed train-only evidence contract

The immutable criterion is
`cycle_001/B2_behavior_pretraining_preregistration_001.json`
(SHA256 `338dd82b1a10f3bda3c2e3c4cea222e61a4411f862d78eba2db362de1a2aeea0`).
It binds `C00_receiver_recorded_v2_001/plan.json` before reading that run's
results or labels. The implementation freeze and execution template are in
`B2_behavior_readiness_implementation_freeze_001.json`. A separate bounded
ledger task must execute readiness; the template is not an execution receipt.

Every admissible row needs this chain:

1. A saved complete control tick and the exact ordered initial/residual
   callback chain. The initial decision must equal the archived controller
   decision. The extra final residual callback is not an additional choice.
2. The actual attempt request ID and exactly one first, non-retry client call.
   Its payload must equal the selected callback's first intent under the
   frozen ProtocolClient transformation: remove `expected_version`, replace
   `request_id`, and bind `owner_id`. Time, source tray and reply must agree.
3. Within the label window, an actual delivered positive ACK belonging to
   that source owner, a unique native empty-transfer leg for the same request
   and tray, matching export/leg-start events, and the actual first physical
   edge. A pending submit reply alone establishes none of these facts.
4. A complete native snapshot preserving all 28,506 business identities and
   consistent actual arrival/completion receipts. Missing or truncated
   segments and unexecuted requests remain explicit exclusion categories.

The outcome is fixed to the negative arrived-unfinished integral over
`[t,t+300]`, in bag-seconds:

`target = -sum_j max(0, min(t+300, completion_j) - max(t, arrival_j))`.

Only actually arrived jobs contribute. An unfinished job contributes through
the window end; no future completion is imputed. Actual receipts establish
arrivals and completions. Later observations may archive the evidence, but
only ACKs/events through `t+300` determine eligibility or the target. Requiring
an eventual receipt after that window would select on a future outcome, so
first actual edge entry establishes execution; any receipt already inside the
window is also checked. This return is the realized continuation under the
behavior controller, including subsequent actions by both owners. It is not
the marginal effect of this single transfer, a counterfactual target, optimal
Q, or a Bellman/FQI target.

The information and fitting limits are fixed:

- `t >= 43200`, so the existing B1 model has already frozen; `t+300 <= 57600`.
- At least 12 unique executed requests, 4 nonoverlapping 300-second windows,
  2 source/destination pairs, and nonconstant targets. These are computational
  readiness checks, not statistical sufficiency or independent samples.
- One whole-trajectory training parent; all flights and all its windows are
  train-only. No development or formal test split is manufactured from this
  trajectory. All 28,506 physical jobs remain in the simulation.
- Fixed 100 epochs, CPU model, seeds 17/29/43. Keep all three final checkpoints;
  there is no best-seed or best-epoch selection from this trajectory.
- Any action model using these labels may first act at simulated time 57600
  or later, with its own label/model freeze metadata. Running from physical
  zero does not authorize earlier use of a model trained on later outcomes.

STD bounds close a flight's arrivals; they do not close its outstanding work,
resource influence, or another flight's congestion exposure. Shared trays and
queues also couple adjacent windows. Therefore a per-STD or chronological
split of this single action trajectory cannot be sold as independent
train/development/test evidence. No private parent mapping is inserted into
actor features. Future independent evaluation requires separately registered
complete parent/day trajectories; cloned same-day jobs with another seed do
not establish new independent flight parents.

## Current evidence and missing work

The historical cyclic run has 352 unique first transfer submissions in
43200–57300. Its final transfer statuses are all rejected and none has a
matching `EMPTY_RECEIVED`; its latest empty receipt anywhere was 21253.633.
These are exclusion evidence, not successful action labels. A small real
callback-chain smoke check binds two callback records to one actual request
and correctly classifies it as acknowledged but rejected. No label was made.

The evidence, reader and explicit resource-revision gates have 53 passing
counterexample tests. The independent strict
stdlib reader matches the frozen producer reader and 24 original actual
callback records byte for byte, with only the documented row schema change.
This decoder check concerns historical rows, not the new run's outcomes.

`C00_receiver_recorded_v2_001` has now legally closed a censored physical prefix
at 54240 with all 28,506 jobs preserved. It contains 2717 actual callbacks,
but does not reach the intended 57600 warmup or 59400 end. Readiness attempt
001 failed because a legitimate conditional-release transfer used the public
job destination as its future source, whereas the extractor wrongly required
that source to equal the tray's current node. The exact callback 32, failure,
old source bytes and regression fixture are retained. The scoped repair
requires a unique public supply/forecast, matching owner, ledger and dependency,
and an already released visible job with that destination. Actual first-edge,
ACK and transport-leg checks remain mandatory; a forecast never creates free
inventory or action authority.

Readiness attempt 002 exhausted its 180-second soft budget after 806 of 2717
callbacks, 113 groups and 693 exact submissions. Its classifications are 636
rejected, 26 executed with a delivered positive ACK, 29 without an edge in the
window, and 2 with an edge but no positive ACK delivered by the window end.
Those partial 26 rows do **not** constitute a completed readiness pass and
must not be fitted. All original partial artifacts remain unchanged.

Resource revision 003 was prepared with a fixed 660-second soft / 720-second
outer limit, zero native calls, zero fits and no automatic retry. It binds
the prior budget failure and the same collection, original preregistration,
criterion and labels. Freeze SHA256 is
`6e836b71813ad4e609ec475a3041d452dbee9355bb7d592494acc7ffddf2dbdc`;
plan SHA256 is
`d7d6c0b7a534a6e708fd080fc291fd09cf4de0dbe8b619619bc6b5ad6d8d6431`.
The separately registered task has now completed in 656.766 seconds internally.
It checked all 2717 callbacks, 368 owner/timestamp groups and 2349 actual
submissions. Counts are 2129 rejected, 81 execution-plus-ACK bound, 81 without
an edge in the window, 4 with an edge but no positive ACK in the window, and
54 outside the closed label window. The immutable minimum passes: 81 unique
executed requests, 26 disjoint 300-second windows, 22 OD pairs and nonconstant
targets. The 26 disjoint windows are still part of one dependent trajectory,
not 26 independent trials. Attempts 001 and 002 remain unchanged failures.

`B2_behavior_training_001/plan.json` was prepared, with SHA256
`7593592bb04dc5e95a16a6422eccf3f44d1d1d7345b999119369cb17613555f9`,
for exactly these 81 training rows. It binds the actual readiness launcher
registration, completed outer assessment, exact three executed source archives,
eligible export, original criterion, arrays parity and complete public-feature
audit. Its fixed limits are 240 seconds internally, 270 seconds externally,
and at most 45 seconds for each of three fits. The registered task has now
actually completed in **126.453 seconds internally / 128.438 seconds
externally**, with source pins unchanged. All three 100-epoch fits and final
weights were saved; all 81 public callback forecasts and feature rows were
materialized. No seed or epoch was selected. The latest actual training label
closes at 53880; the preregistered model-use boundary remains 57600.

The separate training runner and consumer have 57 pure gate tests.
Preparation requires a fully passing readiness receipt
and the exact executed readiness source archive from its closed launcher
attempt. It rechecks each ACK, request, first edge and native leg. The v2
callback schema is normalized on a deep copy only; original callback and
adapted hashes are retained. Fixed 100-epoch weights for all seeds 17/29/43
are saved without selection. Before fitting, the first three eligible
callbacks with genuinely different proposed semantics are fixed as diagnostic
pairs, or fewer if fewer exist. Every seed reports their score gaps under
actual forecasts, masked forecast values and known-demand values set to zero.
Unknown demand remains unknown; static-plan provenance is retained. These
input interventions create no alternative outcome labels or physical benefit
claim and do not pretend to evaluate a separate no-plan product.

`foundation_airport_behavior_consumer.predict_behavior_checkpoint` explicitly
rejects simulated times before 57600 before reading model weights. At later
times it checks the exact model file/content hashes, closed training receipt,
fixed final-epoch plan, schema, mapping, information variant and trained value
implementation. The generic value API is unchanged. The consumer's source
and pure tests alone do not establish native consumption; the separately
executed shadow evidence below supplies that runtime check.

The completed readiness and training tasks establish actual public
forecast/account/action feature consumption and actual behavior-label fitting.
The trained scorer remains advisory: native execution checks and
complete protection evidence must remain external to the model. The current
airport traces do not supply full candidate counterfactual nonharm labels or
a complete receiver inbound account. First training and shadow/native
consumption therefore demonstrate real data consumption only; they cannot
establish improved control, whole-business nonharm, or true multistep RL.

## Actual training and fixed diagnostic results

The fitted network has 88 public features and CPU layers 64/64/1. The saved
full-training forward metrics are:

| Fixed seed | Training MSE (bag-seconds squared) | Training RMSE (bag-seconds) |
| --- | ---: | ---: |
| 17 | 139,668,714.12 | 11,818.15 |
| 29 | 141,164,128.70 | 11,881.25 |
| 43 | 153,645,757.15 | 12,395.39 |

These are fitting diagnostics on the same 81 dependent training rows. There
is no independent development/test error and no reason to select seed 17
from this table. All three are retained for the registered mechanism check.

Before fitting, callbacks 28, 29 and 30 supplied the first three eligible
pairs with different actual proposed semantics. Each of the nine seed/pair
combinations changes its chosen-minus-other score gap when known forecast
values are masked or set to zero. Six of nine reverse that gap's sign under
either intervention. This supports the narrow claim that the fitted scorer
uses flight forecast values differently across actions, rather than adding
the same offset to every action. It does not validate the other proposal's
outcome, establish useful action ordering, or demonstrate native benefit.
The interventions preserve original unknown regions and static-plan source
metadata; no no-plan product evaluation or new labels are claimed.

The independent stdlib review in
`cycle_001/B2_behavior_training_review_001/report.json` verifies all three
actual weight files and content hashes, finite 88→64→64→1 shapes, complete
epoch 0–100 curves, executed source archives, exact outer/inner receipt
binding and diagnostic subtraction arithmetic. It took 0.767 seconds. It
does not recompute model forwards: the MSE column above is explicitly the
producer's saved full-training forward result. Report SHA256 is
`6a24b957e9ec1cbe23155827385f9dd4d2c5c47bca6a4577e568929f67b2aca7`.
The exact model descriptors for the shadow task are saved in that directory's
`shadow_model_descriptors.json`, SHA256
`1b2b6c61e4d73a0a8e1de8de6cccdb124f1b1eadd916a9b9151bb3e9acb0d157`.

The new shadow scorer has 14 pure orchestration tests and an independent
source review. Its two post-57660 callbacks were selected from already
viewed baseline outcomes, with both first edge and positive ACK within
300 seconds. Runtime receives only their frozen callback identities, never
their selected outcome/request/ACK/edge data. This is a mechanism replay on
the same trajectory used for training, not heldout evaluation.

## Actual native shadow scoring and independent numerical audit

`B2_live_behavior_shadow_003` completed the original continuous physical
0→57600→59400 run, with native acceptance passed and no automatic retry.
The inner process took 600.532 seconds and the outer launcher 615.203 seconds.
Its 116 frozen source files were unchanged. The plan SHA256 is
`c9938ccbd541d248b362742e78fef52dc939a877f4bb0c1897f4ba2492150fd4`.
Prepared attempts 001 and 002 remain superseded preparation artifacts, not
additional native runs. Reaching 59400 is the end of this calibration window;
it does not mean that all 28,506 physical jobs completed.

Both registered callbacks actually invoked public B1 prediction, mapping,
six-account feature extraction and all three fixed models inside the native
callback. All original proposals were scored. The wrapper returned the
original baseline decision object; scores did not select or modify an action.

| Actual callback | Proposals scored per seed | Complete scorer wall | Complete recorded callback wall | Scorer process CPU |
| --- | ---: | ---: | ---: | ---: |
| international, 57840, sequence 3582 | 2 | 0.4286821 s | 0.4659217 s | 0.421875 s |
| domestic, 57900, sequence 3585 | 13 | 8.5605733 s | 8.9735710 s | 8.312500 s |

The scorer interval includes validation/imports, forecast, mapping, public
accounts, features, and all three gated model forwards. The complete callback
interval additionally includes baseline planning and all callback recording
and event storage. Process CPU is process-wide CPU consumption during the
scorer interval, not a per-stage native latency measurement. Both complete
callback times exceed 100 ms; no deployment latency claim is supported and
the existing 100 ms / 0.05 s protections were not relaxed.

In the domestic callback, B1 prediction took 0.1466544 seconds, public action
feature construction 1.8166229 seconds, and the three gated model-forward
stages 1.8252210 / 1.7883051 / 1.8184732 seconds. These gated stages include
their validation and feature work; they do not measure the small neural
network alone. A future separately registered optimization can investigate
equivalent reuse within this one immutable public callback. No such
optimization or dynamic-evidence cache is part of this frozen run.

The separate standard-library-only audit
`cycle_001/B2_behavior_training_review_001/shadow_score_audit_001.json`
recomputed all 45 actual saved 88-feature scalar forwards using the three
frozen weight files. The maximum absolute score difference was
`9.313225746154785e-10`; the audit took 0.619 seconds. It also verified the
actual launcher/inner receipt binding, immutable source archives, model file
and content hashes, information cutoffs, unknown forecast preservation, and
timing inclusion. Audit SHA256 is
`5c851ec04cd5fee1ccdff64eadee84967fd9e5c7d8439d5cfa0cf4077f6134ea`.
It imported no training/native code and performed no fitting or native call.

The scorer's sorted canonical callback hash and the wrapper's insertion-order
serialization hash belong to different hash domains. Their equality is not
asserted. The numerical audit binds saved public feature vectors and scores;
it does not independently reimplement feature extraction or join physical
execution. Its immutable report therefore leaves that separate audit required.

The companion independent physical-chain audit has now completed in 48.969
seconds (49.718 seconds including its launcher), with no source changes,
native execution or fitting. It verified all 38,758 blob CRC/hash records and
all 3,978 callback reference graphs, materialized exactly the two selected
public callbacks, and matched their sorted canonical hashes to the scorer.
It then bound each original proposal to its actual first submitted payload,
source-delivered positive ACK, unique native transfer leg and first edge:

| Callback | Actual request suffix | Source→destination | First edge after callback | Positive source ACK delivered after callback |
| --- | --- | --- | ---: | ---: |
| international, sequence 3582 | international:transfer:1942 | 41→138 | 132.85 s | 182.2 s |
| domestic, sequence 3585 | domestic:transfer:9017 | 81→49 | 5.0 s | 62.2 s |

Both satisfy the frozen dual-300-second mechanism criterion. The actual
requests remain baseline requests; scoring did not issue them. Their source
ACK status is `departed`; this is not evidence of a complete receiver-side
inbound account. The audit also established exact baseline parity for every
command payload, reply, retry and ACK, and for the full native result after
excluding only `native_event_ms` and `advance.wall_seconds`. Jobs, trays,
transfers, receipts, leg identities, native counts, population and continuation
semantics all match. Exactly 430 business jobs are complete at 59400 in both
runs; the full population remains 28,506.

The physical audit is
`cycle_001/B2_live_behavior_shadow_003_review_001/report.json`, SHA256
`f140ceea4059d752a3dcd22cc4a542ed282fb4bdd7bf90119a4262c34aef13f8`.
Together the two independent audits establish six actual model invocations
and 45 scalar scores inside the two original native callbacks, followed by
their unchanged real baseline submissions and physical execution. Neither
audit alone is substituted for the other's numerical or physical evidence.

The established scope is actual flight-conditioned model scoring in two
native callbacks with unchanged baseline choices. It does not establish
model-controlled selection, better action ordering, policy benefit, complete
candidate protection evidence, an independent test, or airport multistep RL.
