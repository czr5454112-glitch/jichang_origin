# G4IRSF25 fresh HCA* scale baseline

## Verdict

This is a fixed-window capacity track, not a completed-population TTH track. Whenever canonical completion is below 100%, full-population latency is `NOT_MEASURED`; completed-survivor latency is deliberately excluded.

## Fresh runs

| scale | raw bags | segments | released | planned | completed | complete bags | unfinished bags | parent wall (s) | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2x | 57012 | 87206 | 87206 | 87206 | 87111 | 56917 | 95 | 321.065 | FIXED_HORIZON_CAPACITY_CENSORED |
| 4x | 114024 | 174412 | 117626 | 117623 | 117270 | 70018 | 44006 | 419.947 | FIXED_HORIZON_CAPACITY_CENSORED |

## Capacity interpretation

At 2x, fresh HCA* completed 99.833% of canonical raw bags. At 4x it released only 67.441% of canonical segments within the same window, while 99.697% of released segments completed; canonical raw-bag completion fell to 61.406%. The fixed-window loss is therefore dominated by work that never entered the released cohort, which is direct evidence of the centralized HCA* throughput ceiling. It is not yet a causal CLCR-vs-HCA performance claim.

## Protocol and censoring

- Window: epochs 8260..98259 (90000 epochs), with no admission cap (`max_new_tasks=0`).
- Workload: whole flight manifests are inserted at equal fractions of each same-stream headway; EntryTime and STD shift together, so slack and the storage lifecycle are preserved.
- `parent_wall_seconds` is measured by this Python process around the fresh Java child. G29 exposes only child wall, so its prior parent wall is `NOT_MEASURED`.
- Wall time is a reproducibility/compute-cost diagnostic, not a bag-latency metric and not a cross-machine speed claim.
- `unfinished_segment_count` uses the fixed canonical denominator; `canonical_complete_raw_bag_count` requires every segment of a raw bag to complete.
- Planned segments come from the legacy `outputstarttime.txt` successful-attempt log; unlike `routes.csv`, it includes tasks that first failed to plan and later succeeded.
- No result in this table is described as completed-population TTH unless all canonical segments and bags finish.

## External validation prior

The pushed G29 2x/2.5 m/s result (`origin/codex/g4irsf29-faithful-2x@b8cdd17`) released/planned 87,206 segments, completed 87,111, and completed 56,917 of 57,012 raw bags in both repeats. Child walls were 287.212 s and 293.938 s. This is a provenance check only; it is not silently merged with fresh G25 measurements.

## Reproduction

```powershell
python scripts/eval/run_g4irsf25_hca_scale.py --scale 2 --scale 4
```

Large generated workloads and Java run artifacts stay under `build/g4irsf25_hca_scale/` and are not publication artifacts.
