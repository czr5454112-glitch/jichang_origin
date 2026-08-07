# G4IRSF17 campaign log

## 2026-08-06 — campaign start

- Created `codex/g4irsf17-execution` in an independent worktree from the frozen G16 commit `87de2da583aea8664d2ea219e1ab0629c0c3e590`.
- Preserved the unrelated uncommitted PIBT edits in the user's original worktree.
- Imported the full G17 mainline plan into `docs/`.
- Reused the existing real runtime seams: E4 source arbitration, generation-stamped wakeups, I1 source-order intervention, G2 destination merge grants, bounded PIBT, supervisor and physical shield.
- Confirmed the prior H5 result to explain: total mean `+0.091033238056 s/raw bag`, decomposed as source wait `+0.149550837076` and network time `-0.058517599020` at 8,192 segments.
- Confirmed the existing outcome-free G15 target catalog contains 1,650 I1 entries; G17's stricter real-competition filter retains 1,648 executable opportunities. G17 will rematerialize/execute selected opportunities instead of building a detached source scheduler.

Current action: implement mutually exclusive native source-wait reasons and a pragmatic, resumable I1/model campaign.

## 2026-08-06T01:47:59.435886+00:00 — source_wait_diagnosis: RUNNING

Attempt 1 started.

## 2026-08-06T01:48:03.570423+00:00 — source_wait_diagnosis: COMPLETE

Decision: `I1_BOUNDED_PILOT_AND_START_G2`

Next: Run the bounded I1 pilot, while allocating the next causal budget to destination merge/service-token G2.

## 2026-08-06T01:48:28.713158+00:00 — i1_plan: RUNNING

Attempt 1 started.

## 2026-08-06T01:48:28.766308+00:00 — i1_plan: COMPLETE

Decision: `REAL_COMPETITIVE_I1_PANEL_PLANNED`

Next: Execute matched H_bag pairs and the bounded H_system subset.

## 2026-08-06T01:48:56.800386+00:00 — i1_paired_execution: RUNNING

Attempt 1 started.

## 2026-08-06T02:46:57.640516+00:00 — source_wait_diagnosis: RUNNING

Attempt 2 started.

## 2026-08-06T02:47:01.969517+00:00 — source_wait_diagnosis: COMPLETE

Decision: `I1_BOUNDED_PILOT_AND_START_G2`

Next: Run the bounded I1 pilot, while allocating the next causal budget to destination merge/service-token G2.

## 2026-08-06T04:01:11.263642+00:00 — i1_paired_execution: RUNNING

Attempt 2 started.

## 2026-08-06T04:01:11.867245+00:00 — i1_paired_execution: COMPLETE

Decision: `EXPAND_COMPETITIVE_I1_TO_512`

Next: Sample targeted under-covered I1 strata up to 512 competitive pairs.

## 2026-08-06T04:01:53.708550+00:00 — i1_plan: RUNNING

Attempt 2 started.

## 2026-08-06T04:01:53.873557+00:00 — i1_plan: COMPLETE

Decision: `REAL_COMPETITIVE_I1_PANEL_PLANNED`

Next: Execute matched H_bag pairs and the bounded H_system subset.

## 2026-08-06T04:33:58.845395+00:00 — i1_paired_execution: RUNNING

Attempt 3 started.

## 2026-08-06T04:34:07.963021+00:00 — i1_paired_execution: COMPLETE

Decision: `EXPAND_COMPETITIVE_I1_TO_512`

Next: Sample targeted under-covered I1 strata up to 512 competitive pairs.

## 2026-08-06T04:38:42.718496+00:00 — i1_analysis: RUNNING

Attempt 1 started.

## 2026-08-06T04:38:43.918756+00:00 — i1_analysis: COMPLETE

Decision: `PIVOT_TO_G2_I1_FRAME_COVERAGE_NO_GO`

Next: The current real I1 frame cannot satisfy the source/leg coverage gate; move the primary causal budget to bounded destination merge/service-token G2.

## 2026-08-06T04:40:14.068819+00:00 — state_aliasing: RUNNING

Attempt 1 started.

## 2026-08-06T04:40:14.264975+00:00 — state_aliasing: FAILED_RESUMABLE

'deadline_slack_seconds'

## 2026-08-06T04:49:40.094946+00:00 — state_aliasing: RUNNING

Attempt 2 started.

## 2026-08-06T04:49:40.411268+00:00 — state_aliasing: COMPLETE

Decision: `CANONICAL_ABLATION_COMPLETE_LEGACY_29_UNAVAILABLE`

Next: Retain only runtime-realizable features that reduce sign disagreement.

## 2026-08-06T04:54:34.613842+00:00 — state_aliasing: RUNNING

Attempt 3 started.

## 2026-08-06T04:54:34.947231+00:00 — state_aliasing: COMPLETE

Decision: `CANONICAL_ABLATION_COMPLETE_LEGACY_29_UNAVAILABLE`

Next: Retain only runtime-realizable features that reduce sign disagreement.

## 2026-08-06 — terminal campaign checkpoint

- Source-wait diagnosis completed on 4,898 matched raw bags. H5−off source wait was +732.500 bag-seconds (+0.149551 s/bag), network time was -286.6192 bag-seconds (-0.058518 s/bag), and TTH was +445.8808 bag-seconds (+0.091033 s/bag). Aggregate reconciliation assigned the added wait to the destination merge-token category; this is not a per-bag causal attribution.
- I1 completed 520 pairs (512 H_bag and 8 H_system). Of 248 changed/eligible H_bag pairs, 18 were beneficial, 16 harmful and 214 neutral. The available frame has one source and one leg class, so the frozen support gate is unreachable. All trained candidates remained `TRAINED_NOT_AUTHORIZED`; native activation remains false.
- The G2 eager-token M1–M6 screen completed 24 arms and 20 matched comparisons at 144/512/2,048/8,192 segments. Every hard-safety comparison passed, but exact competitive boundaries and effects were zero because the pending-grant peak was one. Decision: `CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT`; the global G2 no-go is false and the JIT bounded-pending seam remains the next pivot.
- The 39D source-local temporal/pressure observation reduced nearest-neighbor conditional variance from 0.19461 to 0.14111 and sign conflict from 0.813% to zero versus the real native 18D static subset. The exact G16 29D junction snapshot is unavailable at the source decision boundary, so no proxy comparison was fabricated.
- Native exact-lease recovery completed the real 1× `(6,12)` in-flight fault case: recovery count 1, all 23 affected bags completed, and failed/stranded/unsafe counts were zero. The 1× fault matrix has ten informative passing treatments plus one explicitly uninformative EBS treatment. Full A*, global scan and future-route access counters remained zero on executed fault jobs.
- The exact 4× no-fault control reached the 20,000,000-event cap at 10,093/174,412 segments. The protocol therefore reused that row as `CAPACITY_CENSORED_BY_EQUIVALENT_CONTROL` and terminalized the ten non-evaluable 4× treatments as `NOT_RUN_CONTROL_CENSORED`, without synthetic result JSON. Fault advantage at 4× remains `NOT_ESTIMABLE`.
- Fixed-map scale completed at 1× and 2×, then ended `HARD_GATE_FAILED` at 4×/8×/16×. Higher-load progress was 10,093/174,412, 11,123/348,824 and 14,127/697,648 segments respectively. The 16× run used 9,944.125 CPU seconds and 5,174.641 MB peak RSS; its per-node telemetry recorded source queue 49,116, source delay 50,030.751 s and junction queue 32. Queue fields exist for only 1/5 scale rows, so no cross-scale queue bound is claimed.
- Reserving the native event heap preserved exact outputs and reduced two-repeat 1× mean CPU by 3.2863% and worker wall by 2.5787%. It is retained as a scoped optimization, not presented as a capacity fix.
- The baseline ladder is terminal as `BASELINE_ONLY_NO_AUTHORIZED_CANDIDATE`. Final decision: `TERMINAL_WITH_CAPACITY_CENSORING_ACTIONABLE_PIVOT`; `workflow_terminal=true`, `protocol_amended=true`, `scientific_matrix_complete=false`.

Next: implement strictly-local just-in-time service-slot arbitration over a bounded pending set, then address bounded source admission/backlog and event/merge bookkeeping under the same F2/H0/R0 locality and safety contract.
