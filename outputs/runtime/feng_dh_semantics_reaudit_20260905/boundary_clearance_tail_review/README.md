# V5 historical tail pairing

Run `python scripts/eval/audit_feng_dh_boundary_clearance_tail.py` from the repository root with numpy and pandas available. This script only reads completed V5 gzip files, the published historical/control paired extract and isolated OD path table; it launches no simulation. It checks original V5 output hashes, all 43,603 exact segment keys and all 28,506 native bag sums. `summary.json` records source hashes, while `manifest.json` checks the derived artifacts and report.

`by_bag_first_release_hour.csv` counts each raw bag once. In contrast, `top5_percent_bags_by_release_hour.csv` groups the segments belonging to those bags; an EBS second leg can be released hours after its first, so it must not be used to count when tail bags first entered. `admitted_population_300s.csv` integrates exact admission-to-completion interval overlap, not node queue occupancy. `isolated_route_24_to_27_hourly_demand_proxy.csv` is explicitly a workload proxy through isolated distance-shortest routes, not a record of executed paths.

The independent interpretation is in `outputs/reports/feng_dh_boundary_clearance_tail_review_20260905.md`. No delay or penalty is fitted from these tables. Times below an isolated distance-shortest policy route are retained because that route need not minimize physical motion plus per-node service time.
