# G31 airport action-value campaign, 2026-10-20

This is a new experiment contract, authorized by the user's request to continue
GPT Pro's next-stage experiments and quickly identify the operational value of
RL prepositioning. Historical evidence at `13cf8eeb9e9692eaf9eaf8b2ebbaeee8e1001626`
and the documentation-only HEAD `41b27dbe70d629239ff150a721691d98421e98ae` remain
historical. Outputs live in `outputs/experiments/g31_ics_action_value_20261020/cycle_001`.

## Questions and attribution

1. Does ordinary same-owner, same-zone empty return restore useful circulation?
   This is shared infrastructure, never RL benefit.
2. At the same complete physical and protocol prefix, does changing one
   uncommitted empty-tray allocation change the full-population finite-window
   unfinished-work integral or the next real decision?
3. Can independently trained C01/C11 select better actions than the
   corresponding same-information C00/C10 rules?

Reduced waiting for trays, arrival before demand, empty-route occupancy,
receiver reservations, subsequent loading and completed baggage are reported
separately. Native legality and positive ACK do not certify per-bag nonharm.
Unknown unfinished outcomes remain unknown. Evaluation-only interventions
cannot be described as protected production control.

## Frozen common conditions

Use the existing 151-node/227-edge graph, 28,506 jobs, 6,673-job cyclic OD
mapping, node49 empty-transit reserve=1, original service/headway/capacity,
R1 rules and recovery. Add an explicit versioned static loader-role contract
and `local_empty_return` scope to the real native protocol, identity and
checkpoint; default cross-zone semantics are retained.

The 60-second controller opportunity, command delay=2s, publication delay=.5s,
retry period=60s, receiver lease=120s, existing forecasting of already known
tray releases and existing R1 settings are common. Future flight information
is separate from known-job release estimates.

One bounded patch modifies at most one optional, currently uncommitted,
actually available empty tray. Retain other batch actions and re-read current
after each submission. Shared static candidate catalogue: K<=3 including
reference; P=2 actually executed continuations per pair. Fixed requests,
pending ACKs and reception commitments cannot be revoked by a patch.

## Lineage, selection and outcome window

Historical full flow remains a development/mechanism anchor, never a new test
day. New conditional synthetic parent seeds are train 701/702, dev 801/802,
test 901/902. They share the historical template and are not real independent
airport days. Before native collection, input generation and hashes are saved.
Per business identity, sample a deterministic uniform arrival displacement
in [-120,120] seconds from SHA256(parent seed, business identity); clip at zero.
OD, identity, STD/deadline, services and storage release are unchanged.
All policies, fleet sizes and replay descendants inherit their parent split.
This mechanism is an arrival-timing sensitivity experiment, not new demand
volume or a claim of realistic day-to-day variability.

Record an absolute calendar start for every parent; train days precede dev
and test days. Old model gates 43200/57600 remain unchanged for historical
models. Early-window experiments initially collect no-plan pairs. Flight
models must be explicitly trained/bound on earlier closed parents before
early use; do not reset an old model's availability clock.

Fully replay warm-up from physical zero for every branch. No unverified
checkpoint restore. Preserve full native-state hash, controller state,
outbox, delivered/undelivered messages, pending leases and deterministic
exogenous input identity at the intervention. Hashes are evaluator-only.
Do not feed offline state to the actor.

The main pair horizon is 1800 physical seconds after the actual intervention.
Anchor eligibility uses only current public state; choose the first eligible
opportunity in the registered interval and a fixed candidate order. B uses
three intervals (7200–14400, 28800–36000, 54000–57600) for each train parent.
C uses an additional train anchor and two anchors for each dev parent.
No eligible anchor is an empty cell, not permission to search test.

Cost is the sum, over the complete offered job population, of
max(0,min(completion,t1)-max(arrival,t0)); unfinished completion is infinity
only for this censored integral. Preserve finite completion differences,
unknown incomplete jobs, failures, timeouts and rejected submissions.
A pair not reaching a common complete endpoint has no full-window advantage.
Real successor time must exceed action time; residual requests at the same
timestamp are not multi-step transitions.

## Training and promotion gates

First require G0: genuine alternative executed actions with different costs
or real successors. If 12 registered pairs are singleton/no-effect or the
same strong rule dominates, diagnose catalogue/guards/window and stop larger
models. Do not train merely to consume budget.

C01/C11 have independently fitted train-only scalers and models, seeds
17/29/43, at most 5 FQI updates and 100 epochs/update. Compare state/time
reference, simple action interaction and existing small MLP. Dev selection
is failure/guard constraints first, then paired regret/native objective,
then lower computation and fixed lexical model identity for ties. Freeze
all selected models and resource models before opening any test result.
Bootstrap only observed real successors with supported legal actions.
Closed MC labels remain MC labels when successors are unknown.

G1 requires a score-driven different nonretry native submission and its
ACK/unique physical leg/receiver or successor. G2 requires C11 improvement
over same-information C10 beyond numerical precision and measured decision
cost, with no new protected-scope violation. No minimum percentage is
selected after results. Small synthetic samples are directional, not G3.

## Fleet sensitivity

Freeze N=18/22/26. The original eleven loader nodes have two trays each.
Use static role/owner/node groups and layout seed 1701 to order second-tray
removal and third-tray addition, balanced round-robin across owner/role strata.
Preserve nested tray IDs, at least one per original node, and true capacities.
Every N starts at physical zero. No post-warmup tray deletion.
Resource training, if train/dev pairs contain actionable information, uses
the remaining six training jobs for a separately named mixed-N C01/C11 model.
G uses resource-model seed29. Missing prerequisites are reported explicitly.

## Finite work and receipts

Total stop bound: 16 hours from campaign creation, including builds/tests.
Maximum 72 long native branches, 14 short native semantic branches, 12
training chains. Attempts, failed starts after construction, replays and
retries count. Initial long limits: soft600/inner660/outer720 seconds;
short semantic branch90 seconds. Event limits initially retain500000 global
and100000 per advance. Calibrate with A before uniformly changing limits.

Allocation: A4, B12, C12, E4, F8, D16, G14, diagnosis2. Dependencies:
A -> B/C and E/F -> all models/dev selection frozen -> D/G. E/F and any
resource-model training may not be invented after seeing D. R1 and R2
latencies are measured separately; synchronous paused simulation time does
not establish a real-time guarantee. Keep current-safe fallback.

Every launch records immutable input, binary, source archive, task
configuration, parent, variant, branch budget and actual receipt. Ledger
updates are append-only. A failed attempt is retained. No main merge.
Research-branch publication follows the user's adopted next-stage instruction.
