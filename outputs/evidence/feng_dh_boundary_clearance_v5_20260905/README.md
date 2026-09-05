# V5 campaign evidence

**HCA scientific qualification:** 43 of 60 historical HCA cells have a positive `generated - completed - active_routes - unfinished` segment-accounting residual. These 43 are invalidated as evidence for no-loss physical performance/capacity comparisons. The other 17 only lack this detected residual; this does not prove full correctness. All observed numbers remain unchanged. Identity/archive/normalization PASS is not HCA execution validation. See the [notes](control_scientific_qualification/control_completion_notes.md) and [60-cell evidence](control_scientific_qualification/control_completion_notes.json); `campaign_manifest.json.scientific_interpretation` records this separately.

This is the separate, user-adopted boundary-clearance V5 reconstruction. Its source identity is 7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7 and its formal JDK18 class identity is a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869. It is not a source-exact reproduction. Prior campaigns and audit opinions are preserved.

`campaign_manifest.json` lists actual, missing, and failed cells. COMPLETE means 60 new V5 plus 120 historical controls passed the recorded identity/data checks; it does not mean all 120 controls are scientifically valid or every baggage population completed. Clean DEADLOCK/HORIZON_REACHED outcomes retain every unfinished bag. The 2x timing prohibition remains even if a method completes.

Primary THT min/mean/max (and diagnostic P95/P99) is the per-raw-bag sum of segment completion minus the shared canonical scheduled release. Native admission-based THT is secondary. HCA actual integer release_epoch is explicitly distinct from canonical D. TH is the number of completed raw bags by fixed absolute epoch 98259; completion/on-time rates, unfinished counts and backlog are separate columns. The optional per-hour normalization divides by 98259 seconds measured from model time zero, not by the active operating window or wall time; it is not an estimate of conveyor capacity. Source backlog ends only when all segments are admitted and therefore includes the EBS schedule gap.

Confidence intervals resample the ten matched workload seeds, not individual bags. All ten eligible seed pairs are required before estimating a comparison. No incomplete bag cohort or available-seed subset is substituted. Lower values are preferred for latency/backlog/tardiness and higher values for throughput/completion/on-time measures. Win/tie/loss counts use the reference method's direction and retain adverse outcomes.

Each available V5 cell stores all native bags and segments as deterministic gzip, plus the original summary/events/runner status and normalized result. Workload canonical/raw/identity bytes and maps are preserved. HCA stores every exported segment and raw timing; canonical records account for unreleased segments omitted by HCA. G31 control JSON contains native aggregate distributions and original integrity checks, not a retained complete per-bag payload. Old HCA execution source/class hashes were not recorded; this limitation is not repaired retrospectively.

`support/support_manifest.json` indexes the 522-OD preflight JSON/gzip, coverage tables, exact compile identity, acceptance protocol, command plans and runner contract checks. The verifier connects each V5 runner's preflight/compile/protocol hashes to these portable copies. Dynamic execution/orchestration files are frozen only after all 60 V5 cells finish; a partial manifest lists them as pending.

Archive records retain their original absolute provenance but can be verified without those paths: locate the suffix beginning at this evidence directory's name and validate archive SHA and gzip-decompressed source SHA. The verifier uses only committed files:

```
python scripts/eval/export_feng_v5_campaign.py --verify-archive
```

To refresh from finished local runs (including partial progress):

```
python scripts/eval/export_feng_v5_campaign.py --archive
```

Final publication should use `--archive --require-complete`; unfinished processes are never read as completed cells. Native CSV trace=0 exports do not prove per-tick collision freedom or reveal actual edge queues. Separate Java fixtures/OD checks support implementation semantics. V5 body-clearance interpretation and its 2,000/h same-incoming bottleneck remain disclosed assumptions; the user selected this candidate after seeing its original map2 results.
