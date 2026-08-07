# G4IRSF18 new ideas and evidence

This notebook is append-oriented. An item is **verified** only when a code path,
test, or native experiment supports it; untested directions remain hypotheses.

## 2026-08-07

### Put the policy boundary at the natural service opportunity

**Verified predecessor evidence.** G17 observed zero live multi-request choice
boundaries even when the eager merge-rule screen reached 8,192 segments. A
request-time score therefore cannot establish control ownership: the first
request has already reserved the future slot before later requests exist.

**G18 implementation decision.** J1/J2 register requests in one bounded local
pending set and choose only when the destination's next natural service
opportunity occurs. `candidate_count > 1`, a changed winner, and the resulting
native action are recorded separately. This makes it impossible to count a
singleton score or a shadow proposal as an action mutation.

### Keep opportunity and candidate denominators distinct

**Implementation decision.** The native learning trace uses one row per
candidate but one `opportunity_id` per service boundary. Reports use the group
count for action ownership and the row count only for model/data volume. This
avoids making a larger candidate set look like more independent decisions.

### Research control needs a resource budget, not a fake promotion

**Verified repository fact.** G17 already separates a learned proposal from
the final supervisor/shield action, but its available I1 artifact is correctly
`TRAINED_NOT_AUTHORIZED` for production and produces no validation override.

**G18 design direction.** A research-only controller may execute on a fixed
workload after basic safety checks while production remains fail-closed. The
authorization state carries a coverage cap, per-segment override and hold
caps, and a kill switch; none of these flags can rewrite a production gate.

### Diagnose event amplification by work per physical opportunity

**Hypothesis to test.** `events/completed bag` alone can rise because the
physical workload has more merge opportunities. The more diagnostic ratio is
`scheduled wakeups / natural service opportunity`, paired with duplicate,
coalesced and stale-generation counts. A healthy event-driven JIT merge should
approach one live wakeup per resource generation rather than one timer per
pending request.

### Preserve diversity with bounded per-incoming frontiers

**Hypothesis to test.** A single global top-K pending set can be bounded yet
silently erase a low-rate incoming edge under heavy traffic from another edge.
Keeping one or two frontier requests per incoming edge, followed by a small
global cap, may preserve both bounded memory and real fairness. Starvation age
still remains a deterministic final guard.

### Use event cost in the counterfactual advantage

**Hypothesis to test.** Two actions with nearly identical bag-time outcomes can
have very different retry/wakeup consequences near the 2x capacity knee. G18
labels should therefore include a bounded event-cost term and report its
ablation; otherwise a learned controller can improve short-horizon queue time
while worsening the high-load failure mechanism.

### Make evidence trace and capacity mode separate experiment contracts

**Verified native evidence.** A 43,603-segment J1 run with candidate-row
telemetry retained consumed more than 16.6 CPU minutes and about 570 MB before
being terminated. With opportunity-row retention disabled, the matched
43,603-segment J0/J1/J2 runs completed in 28.68/24.89/24.48 wall seconds. J1
and J2 still reported 158,633 and 160,699 core opportunity events while storing
zero candidate rows. Hard safety passed for all three arms.

**Implementation decision.** Evidence prefixes through 8,192 retain bounded
candidate rows. The 43,603 ladder and every scale job use capacity mode: trace
rows are disabled, core counters remain authoritative, and `telemetry_mode` is
persisted in the plan, result, CSV and report. This turns observer cost into an
explicit protocol variable instead of confusing it with controller scaling.

### Test pending repair and in-flight exact leases with distinct temporal gates

**Verified native evidence.** The generic 35% edge-(6,12) fault window exposed
10 bags and preserved J1/J2 pending competition (peaks 5/7), but it fell in a
gap between physical traversals and therefore produced zero in-flight lease
recoveries. The J1 trace exposed request 2,081's flight window
`[16961.01816, 16971.01816]`. A single preregistered calibration at its midpoint
`16966.01816` produced exactly one in-flight fault-generation recovery in each
of J0/J1/J2, with three affected bags, hard safety, fault+repair delivery and
zero outstanding requests all passing. The first of at most three allowed
onsets succeeded, so no further scan was run.

**New implementation direction.** A future deterministic regression hook could
inject a fault after the Nth observed entry on a named edge. That would preserve
the same real runtime semantics while avoiding a workload-specific absolute
timestamp. Until implemented and tested, the evidence-directed midpoint stays
research-only and its source opportunity is recorded in the plan.

### Treat the 2x improvement and 4x wall boundary as a scale knee

**Verified native evidence.** On the formal source-queue workload, J1/J2 reduce
mean TTH versus J0 by 2.562/2.523 seconds at 1x. At 2x the reductions grow to
435.316/542.845 seconds; J2 is 107.529 seconds better than J1 while using 223.907
versus 222.337 events per raw bag. All six 1x/2x results complete with hard and
algorithmic safety.

At 4x, all three matched arms reached the external 1,200-second wall boundary
without a native return or observed event-cap result. Their verified CPU lower
bounds are 1199.844/1154.875/1151.969 seconds and the observed RSS snapshots
are 770.453/770.344/741.488 MiB. Completion, TTH, event counts and algorithmic
safety are therefore unknown, not zero or failed. The progression rule blocks
8x/16x full and 32x smoke rather than manufacturing larger-scale rows.

**Hypothesis to test.** The sharp 2x benefit shows that delayed local arbitration
matters most after congestion becomes nonlinear, while the matched 4x timeout
shows a shared runtime-capacity bottleneck that policy ranking alone cannot
solve. The next scale work should profile event-loop and queue operations in
capacity mode and introduce a resumable/externally bounded worker before
reopening the 8x/16x/32x gate.

### Spend ownership on opportunities that can actually change the action

**Verified native evidence.** The research-only J7 ladder exercised real local
ownership without changing topology or enabling production. At 2,048 segments,
full coverage applied 137 learned decisions but only three selected a
feature-distinct action. At 8,192 segments, 919 applied decisions produced 44
distinct mutations; matched mean/p95/p99 TTH stayed unchanged, mean merge wait
fell by 0.035962 seconds and the event count fell by six. At 43,603 segments,
capacity-mode telemetry remained off, hard safety and every native contract
gate passed, and 3,500 applied decisions produced 154 distinct mutations. The
matched mean TTH delta was -0.004653 seconds, p95/p99 were unchanged, mean merge
wait fell by 0.018039 seconds, and the event count rose by 228. The campaign
therefore remains research evidence only and both production authorization
signals remain false.

**New implementation direction.** Uniform coverage spends most of its budget
on decisions where J7 agrees with J2. A next research arm should learn, in
shadow first, a local `will_change_J2_action` likelihood and allocate the same
bounded ownership budget preferentially to high-likelihood opportunities. The
objective is higher causal-action density (distinct mutations per applied
decision), not more nominal ownership. Selection should retain the existing
local feature contract, starvation guard, per-segment cap, kill switch and J2
fallback, and include an event-cost penalty because the full-scale result shows
that small queue-time improvements can coexist with modest event amplification.
