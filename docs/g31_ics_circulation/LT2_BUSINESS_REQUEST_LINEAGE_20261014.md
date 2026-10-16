# Complete-request lineage: source census and proposed finite update contract

2026-10-14. Design and static census only. Frozen policy code, native021 behavior,
bundle002 totals and the compiled native022 timing artifact are unchanged.

The attached LT2 plan §9.1 requires spans by business `request_id` and causal
parent chain, including legal observation, prediction, candidates, solve, actual
source/receiver validation, commit and ACK processing. Computation, logical
transport/queue wait and end-to-end completion are distinct. Shared work cannot
be divided across jobs to make a slow activation pass. A measured sample is not
a hard-real-time proof.

## What the current interface actually identifies

There are four different identities:

| Identity | Current evidence | Limit |
| --- | --- | --- |
| Physical task | `business_bag_id` on local job contracts and route commands | Identifies the bag, not an independently accepted update request. |
| Owner activation | owner, owner epoch, notification sequence/timer/tick | Existing complete coarse ledger roots use this proxy scope. One activation can mix many jobs, ACKs and housekeeping actions. |
| Protocol operation | immutable `request_id` in client outbox | Begins after some observation/preprocessing; cannot alone identify the full business request. |
| Business update/obligation | No general admission API or complete continuation graph | Cannot be reconstructed reliably by parsing IDs or dividing an owner activation. |

Native notifications currently expose only owner-local sequence, observed time
and change-mask. Multiple reasons may be coalesced; no per-job update identity or
specific ACK ID is carried in that notice. `refresh` can identify actually read
ACKs, but absence of a matching ACK ID in the notice is not independence proof.

R2 selection has a separate loss of structured provenance: `transfer_candidates`
selects a concrete demand, but its emitted intent does not include a structured
selected demand/job identity. The candidate ID embeds a job string and is then
replaced by `ProtocolClient.submit`. Parsing that string is not an acceptable
identity contract. `terminal_receiving_pressure` is a port-capacity obligation,
not a physical bag despite its synthetic `port-clear:...` identifier. A hook must
capture the selected demand record at the choice itself, before ID replacement.

The [static inventory](../../scripts/experiments/g31_ics_circulation/request_lineage_inventory.py)
finds eight controller `client.submit` sites, two `_send` call sites and two
native submit endpoints. Its five tests detect new, missing, duplicated and
dynamically unclassified sites. This is a syntactic coverage guard, not evidence
that runtime business lineage exists.

## Every current submit path and its unresolved branches

Each entry below needs an explicit hook before payload copying/ID allocation.
`continue` means the same accepted obligation remains unresolved. `new` requires
an independently admitted update with a finite completion contract. Where the
current code lacks the evidence to choose, the result is **unknown**.

| Source site and condition | Classification and required evidence |
| --- | --- |
| `ProtocolClient.submit → _send(retry=False)` | Generic new protocol operation, **not automatically a new business root**. Require its creating update and obligation IDs before `copy.deepcopy(payload)` and `next_id`. |
| `ProtocolClient.refresh → _send(retry=True)` | Exact immutable transport retry continues the existing protocol operation/obligation. Preserve payload hash and attempt count; include query/copy/ACK processing even if no retransmission occurs. |
| `_publish_owner_demand` and periodic `run_protocol_control`: no prior channel publication | Child of the update asking to publish this owner's demand. This is a snapshot-delivery obligation, not one root per remote queued bag. |
| Same demand sites: prior delivered capture signature differs | A new local queue update can request a new publication while referring to the settled old capture. Under a declared one-shot publication contract this is a new update; old capture is a reference, not a completion parent. Current merged causes do not prove the admission identity: **unknown** until recorded. |
| Same demand sites: failed/rejected/expired prior publication after cooldown | Continue if retrying an unresolved publication obligation; new only if that obligation was explicitly terminally failed and a separate update was admitted. A fresh native ID alone proves neither. Current code: **unknown**. |
| `_publish_services` route: no active route for the exact owner/tray/job/generation/traversal/node key | Child of an admitted routing update for that exact service state. A new physical stage identifies a subject change but does not itself provide a business update ID. |
| Route: old terminal status not `updated`, same key after cooldown | Recovery/replacement continuation if the accepted route-update goal remains open. Otherwise an independently requested update must be explicit. Current code: **unknown**. |
| Route: route/fault signature changed while old status is `updated` | Usually a new routing update on newly delivered information; could also resolve a still-open coupled obligation. Record trigger and accepted contract. Reading the installed route is not enough to attach the old root. Current code: **unknown**. |
| Route: old `updated` lease reaches expiry | Contract-dependent renewal, described below. Current code: **unknown**. |
| `_publish_services` forecast: no old forecast for service key/next hop | Child snapshot publication of a routing/service update; record observed condition, exact local stage, target and finite publication goal. |
| Forecast: retired without publication after rejection/expiry | New ID can be recovery of the original unresolved publication. Record prior failed ID and obligation, including whether a published `result_id` ever existed. Current branch alone cannot close the old goal. |
| Forecast: old withdrawn, replacement after refresh/expiry/condition change | Replacement belongs to the retirement episode that required it, through the withdrawal ACK and `replace_at` timer. Preserve this episode ID through waits. Whether the episode continues the original snapshot or is a new maintenance update depends on the accepted contract. Current code: **unknown**. |
| `_publish_services` withdrawal: `condition_changed`, `stage_or_route_changed`, `refresh_due`, `expired` | The payload's exact `forecast_request_id` is a subject reference. Link to the update that requires retirement. It is not automatically a continuation of a previously completed publication. If that publication's accepted goal included maintaining/revoking it, the old obligation is also a parent. |
| Withdrawal: prior withdrawal rejected after cooldown | Continues the same unresolved retirement episode; preserve that episode while creating the fresh native ID. Transport retries still reuse the exact old native ID. |
| `_activate_owner` and periodic `run_protocol_control` transfer: first selection | Child of admitted dispatch/prebalance update; capture exact chosen supply and demand before native request construction. A port-clearing obligation must retain its true capacity scope. |
| Same transfer loop: residual matching after an accepted pending submit | Still work of the same decision episode, including the fresh observation, candidate construction, matching and output; all inseparable shared preparation is fully charged to every dependent operation/root. It is not another external update merely because it creates another native ID. |
| Transfer after a later rejection/cooldown/forecast or physical change | Current code reruns general matching without an explicit replacement-operation link. Same tray/destination is insufficient proof of continuation; a different tray is insufficient proof of independence. Require the same unresolved assignment obligation or independent admission; otherwise **unknown**. |
| `complete_protocol_route` | Closest existing one-shot API: receives caller request identity before legal observation and includes conversion/A*/codec/submit/native advance/retry/response. It has no exhaustive new-business-root contract or graph; keep its documented simulated one-request scope. Timed-out results remain unknown, not completed failures inferred from offline state. |

The current event/periodic controller does **not** create `cancel_transfer` or
`planning_snapshot` commands. Research adapters/direct native calls are outside
this census and need their own admission/lineage hooks. Generic `ProtocolClient`
users cannot inherit coverage merely because they use the same transport class.

## Renewal is determined by the accepted contract

Two contracts are materially different and must be declared before measurement:

* `one_shot_snapshot_delivery`: deliver one source-captured snapshot, process its
  actual ACK and settle the resulting update. A later expiry/refresh starts a
  separately admitted maintenance update; withdrawal/replacement and retries are
  children of that maintenance episode. The old snapshot is a reference. This
  contract does not promise an indefinitely fresh forecast or successful future
  transport based on it.
* `maintain_until_public_stage_end`: keep this specified service-stage estimate
  refreshed and withdraw it on the declared visible end/change. Renewal, failed
  withdrawal and replacement remain continuations of the original obligation
  until that finite public completion condition is reached and cleanup is done.
  A recurring timer cannot silently end it. If the stage never ends or its end is
  not legally observed, it remains open/censored, with all computation retained.

The analogous route distinction is “process and acknowledge this finite route
update” versus “maintain an admissible route until a specified public stage end.”
An `updated` ACK settles only the first contract. A future physical failure or
new fault may produce a new independently admitted update, but cannot erase a
required fallback from the earlier unresolved contract.

Current source does not choose one business contract for these lifecycle paths.
This document does not retroactively choose the cheaper one for saved traces.
For new experiments the declaration must be tied to the actual user-facing task
update service. The owner-activation proxy remains a proxy under either choice.

## Minimal diagnostic hook contract

The next implementation should emit a sidecar event stream with immutable IDs;
its facts never enter policy choices or native physical state. The first genuine
per-task admission interface must receive a caller update ID and task ID **before
observation**. Merely splitting a later owner record into its observed bags is
insufficient. Existing autonomous runs can start with explicitly scoped owner
update roots until such an interface exists.

| Hook | Required record |
| --- | --- |
| `update_accepted`, before any observation or payload preparation | `update_id`, scope (`business_task_update` only for genuine task admission; otherwise `owner_activation_proxy`), owner, supplied task/obligation subjects, finite `completion_contract_id`, exact public trigger identities, monotonic accepted time, logical accepted time. |
| Before `_activate_owner` and every periodic owner action | Decision episode ID, actual root set, separately listed independent trigger roots and unresolved continuation parents. Mixed causes stay mixed; don't reduce them to a single mask-derived reason. |
| `refresh`, before each query and after returned ACK processing | Protocol ID, attempt, actual last-delivered sequence/status before/after, root/obligation lookup, required result-handling disposition. A repeated unchanged ACK poll is still continuation computation for that operation, but does not automatically own every later independent solve. |
| At each branch in the table, before `submit` | `branch_id`, creating episode, obligation IDs, `continues_obligation` parents, `references` separately, explicit reason and completion disposition of predecessor. Unclassified branch emits unknown. |
| At route/forecast retirement and replacement state transitions | Stable retirement episode ID, condition/lease trigger, referenced old operation, required withdrawal and replacement obligations, every coalesced update whose desired condition must be satisfied. Preserve through `retire_reason`, `withdraw_request_id`, `replace_at` and cooldown waits. |
| At matching choice and residual loop | Selected structured demand record, supply/tray, goal type, dependent business update IDs, initial versus residual decision episode. Retain the full shared preprocessing/solve interval for every dependent root. |
| At `ProtocolClient.submit/_send` | Native immutable ID, payload hash, creating operation/obligation, attempt identity, fresh/retry flag, synchronous admission reply. No lookup by string parsing. |
| Native022 rows | Bind actual source/receiver validation, commitment, outcome and ACK handling to protocol operation IDs via immutable native tables. These are measured phase facts, not business-root admissions or proof of delivered terminal ACK. Whole native envelopes and unclassified remainder remain conservatively charged. |
| Timer scheduling and delivery | Timer identity/generation and the obligation/episode that armed it, with declaration `continuation` or `new_maintenance_update`; preserve original trigger timing across segment/restore. A timer key alone cannot decide this semantic category. |
| Decision/continuation seal | Exhaustive declared outcome: no action, failure with no required fallback, or exact required child obligations. This seal must occur after the policy has decided whether to replace/replan, not merely when ACK refresh first sets terminal. |
| Drain and returned output | Link the actual complete native timestamp after the last required owner action and the measured serialization/return interval. Any budget cut before drain/output keeps the relevant roots open. |

Store `references`, `reads_state_from` and `continues_obligation` separately.
For example, update B can read A's granted reservation and intentionally choose
no action. B's read and solve belong to B; A still receives its own query/ACK/
retry work. Conversely, if B is actually the recovery step required to complete
A's unresolved goal, that same no-action decision is charged to A. No-action
does not imply independent; reading A does not imply continuation. The admission
and disposition contracts distinguish the cases.

## Conditions for closing a root

All conditions are required, with no post-hoc optimistic inference:

1. Its finite requested goal has a legally observed outcome or an explicit
   terminal failure allowed by its accepted contract. An expired lease, pending
   grant, lost ACK, timeout, owner outage, unknown validation or offline successful
   receipt alone cannot settle it.
2. Every required child operation has an actual delivered terminal ACK processed
   by the owning client, or an actual synchronous rejection handled by the
   decision. Source and receiver validation can be not-applicable for a genuine
   earlier rejection, but must not be fabricated as zero-duration successful
   stages. Native phase coverage remains a separate gate.
3. The decision seal identifies all mandatory retries, cancellations, replacement
   and fallback. They are settled or remain explicit open children. A new native
   ID cannot hide an open obligation. A later independent update cannot reopen a
   fully settled old one solely because it references its prior result.
4. Shared work, all mandatory post-action native drains, client/output encoding
   and returned output are measured. The final budget-cut root cannot close while
   `needs_native_drain` is true. Required children spanning checkpoints retain
   their identity and accounting; restore work has an explicit shared cohort.
5. All traversed paths have classified lineage, no missing record/source hook or
   clock/identity/coverage error. Unknown classifications remain unknown, with the
   old conservative same-owner bound still available. Rejecting a performance
   certificate does not delete the request from any denominator.

Logical wait can exceed 100 ms without proving compute exceeds it; all CPU/wall
service segments and their maximum continuous duration must still be retained.
No native/physics discount is authorized by this lineage design. Refinement
requires both exhaustive semantic parent classification and measured complete
phase coverage, not either one alone.

## Concrete next experiment contract, not a replacement acceptance criterion

The next genuine task-update interface should accept a caller-supplied update ID,
one business task ID, owner, public trigger and finite desired update **before**
reading the task or building features. The operation graph then has two distinct
relationships: `continues_obligation` for computation required to settle that
update, and `references` for already available state used by an independently
admitted update. A later independent dispatch decision B reading A's reservation
does not extend A. A retry, delayed source/receiver validation, actual commit,
delivered-ACK handling, or required fallback of A remains attached to A's original
immutable protocol identity. Fresh message IDs cannot break that chain.

For a new experiment, declare the finite service being measured in advance:

| Operation goal | Legally observed settlement and outstanding limits |
| --- | --- |
| Install this authorized local R1 next-hop preference | Actual source execution and permission validation, followed by matching delivered `updated` ACK, processed disposition, mandatory drain and returned output. This does not grant a full suffix or prove a later hard receiving reservation. If the goal includes execution of the selected hop, the matching actual hop must also be legally observed; a route string or ACK alone is insufficient. |
| Commit this R2 export/reception decision | Actual source permission/stock checks, receiver permission/capacity checks and committed reception lease, followed by an ACK that proves that exact commitment. A forecast, pending admission or future predicted availability cannot satisfy it. Native `EXPORT_GRANTED` timing is offline evidence, not by itself owner knowledge. |
| Complete the existing R2 transfer operation | Preserve the current client's contract: actual delivered `received` ACK or permitted terminal failure, required handling/fallback, drain and output. Its `dispatching`/`departed` ACKs remain nonterminal in current code. All later immutable retries/ACK work remains in this operation's ledger. |
| Publish a conditional forecast | Delivered snapshot ACK only settles snapshot publication. It neither grants a tray nor settles an R2 export/reception request relying on that forecast. |

The first two are explicit experimental update-stage contracts, not assertions
that the user accepted narrower LT2 completion semantics. The existing R2 client
continues retries until its terminal outcome, so an installation-stage timing
cannot replace that complete immutable-operation total. Report both if a new
stage API is implemented. Do not retroactively close saved R2 roots at
`EXPORT_GRANTED`, or relabel later compulsory retries as independent maintenance.
Likewise, physical business-job completion is a separate outcome: an installed
route can settle a finite update while its job remains in transit, but normal-job
protection still needs the complete declared business outcome.

A no-action update may settle only after its lawful incumbent/no-action decision
and all required validation, fallback disposition, drain and returned output are
complete. Unavailable permissions or an unconfirmed forecast do not become a
zero-cost successful no-action result. Coalesced multi-job owner activations
remain proxy/cohort measurements until a real task admission supplies those
individual update identities; shared computation is never divided to fit 100 ms.

The prepared [5,000-update native022 experiment](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_5000_prepare_001/plan.json)
still measures owner-activation roots and complete conservative bundles, plus a
partial native phase partition. It retains the whole native envelope and every
unattributed remainder. It supplies implementation evidence for this next
interface; it cannot certify an unimplemented business-update contract.
