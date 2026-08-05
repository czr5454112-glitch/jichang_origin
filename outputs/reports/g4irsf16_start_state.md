# G4IRSF16 start state

## Takeover outcome

G4IRSF16 starts from commit `8f3106b116f2648b6fa2e30bc8960659739d3a58` on branch `codex/g4irsf16-execution`. It inherits the published G4IRSF15 formal statuses `PASS_CAUSAL_GATE` and `PASS_CAUSAL_GATE_VALID`, including 2,172/2,172 action-changing labels (I3=1,086, I4=1,086) and 256 H_system pairs.

No new validator, hash system, causal campaign, map, task stream, or scaled workload was created. The fixed inputs remain `data/processed/maps/map2.json` and `data/processed/tasks/inputdata.jsonl`; the G4IRSF16 scale count is zero.

## Validator attempt in this worktree

The inherited validator was attempted before implementation. A newly checked-out Windows worktree first exposed a byte-level source binding difference in `cpp/ics_core/bindings/czr005_cpp.cpp` caused by line-ending materialization. The validator was then launched from the untouched G4IRSF15 worktree with the project Conda environment and exact predecessor bytes. It exceeded both bounded observation windows (120 s and 600 s) without reporting a semantic gate failure; the surviving child processes were stopped so they would not consume the machine in the background.

This round therefore does **not** claim a fresh validator pass. It relies on the published predecessor formal release and records the bounded attempt honestly, then spends the implementation budget on data, models, native runtime, shadow, and closed-loop evidence as required by the plan.

## Mechanism comparison boundary

The formal causal labels and the new runtime trace use E4 destination-merge-request semantics with M0/off supervision. The historical F2 and v2-safe headline means were produced under E0. A fresh E4 supervisor-off control is required for any causal closed-loop comparison; E4 candidate results must not be presented as a direct win over an E0 number without a matched-mechanism qualifier.
