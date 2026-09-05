# CIE external-baseline shutdown checkpoint — 2026-09-05

Checkpoint time: `2026-09-05T08:28:57+08:00`.

Status: **INTERIM / INCOMPLETE**. The external-robustness campaign contains
`161/180` validated normalized cells. All `90/90` map2 cells and all `60/60`
Nanning HCA/G31 cells are complete. The long-running Nanning CIE-DH port has
`11/30` complete cells: `7/10` at 1x, `4/10` at 1.75x, and `0/10` at 2x.
This checkpoint is for review and shutdown recovery; it is not a final
cross-map performance claim.

## Results available at the checkpoint

| map/load | valid CIE-DH seeds | mean completed | completion rate | mean on-time | on-time rate | formal population latency |
|---|---:|---:|---:|---:|---:|---|
| Nanning 1x | 7/10 | 12,693.714 / 28,506 | 44.52997% | 12,327.143 | 43.24403% | N/A: every cell is full-population incomplete |
| Nanning 1.75x | 4/10 | 22,050.000 / 49,765 | 44.30825% | 14,126.750 | 28.38692% | N/A: every cell is full-population incomplete |
| Nanning 2x | 0/10 | not yet measured | not yet measured | not yet measured | not yet measured | N/A by the frozen 2x protocol |

The completed-cell ranges are narrow: Nanning 1x completes 12,690–12,701
bags, while Nanning 1.75x completes 22,047–22,052. This is an early, internally
consistent signal that the unchanged map2 partial state machine is not viable
on Nanning under the frozen port. It must not be back-attributed to Feng's
original CIE-DH, because Feng reported no Nanning experiment and the original
CIE-DH source was not recovered.

On the already complete map2 10-seed campaign, the executable partial CIE-DH
and G31 are mixed at 1x: averaged across seeds, G31 has 1.79% lower mean
population latency, but 15.32% higher P95, 25.19% higher P99, and 42.07% higher
maximum latency. At 1.75x G31 has lower mean/P95/P99 timing, while maximum
timing wins are seed-dependent. At 2x formal THT is N/A for every method; the
business completion, on-time, tardiness, and backlog rows remain the valid
comparison surface. No universal G31-over-CIE-DH claim is supported by this
checkpoint.

The historical Table 5.3 measurement remains the sole primary performance
anchor for Feng's original CIE-DH. The independent Java reconstruction is
secondary executable evidence only. Its deterministic map2 result is
optimistically biased relative to Table 5.3: mean 238.7023 s versus 265.5921 s
and maximum 326.0 s versus 517.2 s.

## Completed coordinates

- Nanning 1x: `104729`, `130363`, `155921`, `205759`, `232003`, `283303`,
  `308081`.
- Nanning 1.75x: `104729`, `181081`, `257053`, `308081`.
- Nanning 2x: none at this cutoff.

The compact per-cell values and result hashes are in
`outputs/tables/cie_external_baseline_checkpoint_20260905.csv`. The complete
available aggregate is in
`outputs/reports/cie_external_baseline_robustness.md` and is explicitly marked
`INCOMPLETE (161/180)`.

## Shutdown boundary

At the checkpoint, twelve non-checkpointable Java cells were running:

- Nanning 1x: `181081`, `257053`, `333667`;
- Nanning 1.75x: `130363`, `205759`, `283303`, `333667`;
- Nanning 2x: `104729`, `155921`, `205759`, `257053`, `308081`.

Seven coordinates had not started:

- Nanning 1.75x: `155921`, `232003`;
- Nanning 2x: `130363`, `181081`, `232003`, `283303`, `333667`.

An operating-system shutdown invalidates only the twelve in-flight cells; the
eleven completed cells above remain valid. Resume must retain those eleven,
force-rerun any interrupted `running/null` coordinate from the beginning, and
then run the seven untouched coordinates. Partial native output must never be
normalized or counted.

## Frozen executable identity

- reconstruction source bundle SHA-256:
  `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`;
- compiled Java class bundle SHA-256:
  `d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286`;
- reconstruction manifest SHA-256:
  `abc496f173c517b2cd224356f3e9f4c5c2b21d1f525ebf570e4dac6ea510d2a4`;
- fixed observation horizon: `98,259 s`;
- no topology-specific tuning, artificial delay, survivor timing, shortened
  horizon, or partial-result normalization is permitted on resume.

## Review decision requested

GPT Pro can decide whether the remaining Nanning port cells are worth their
large compute cost. Stopping them does not invalidate the complete map2
10-seed evidence, the historical Table 5.3 anchor, the Java reconstruction,
the HCA/G31 native runs, the critical-load experiment, or the completed
ablation evidence. Continuing them would complete the pre-registered
cross-map robustness matrix, but should not be justified as recovery of the
unavailable original CIE-DH implementation.
