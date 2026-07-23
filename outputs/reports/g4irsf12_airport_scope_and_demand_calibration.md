# G4IRSF12-K Airport Scope and Demand Calibration

Date: 2026-07-23

status: `PARTIAL_WITH_EXPLICIT_BLOCKER`
calibrated_multiplier: `UNKNOWN_NOT_COMPUTABLE`
finite_uncertainty_interval: `UNBOUNDED_MISSING_SCOPE_AND_DESIGN_DAY_INPUTS`
phase_l_status: `BLOCKED_NOT_RUN`

## Decision

The immutable input is a validated 28,506-bag historical clock-day with a strong banked arrival profile. It is not proven to be an ordinary day, design day, or peak day. No primary evidence located identifies Chengdu versus Chongqing, the terminal, the local/transfer scope, the represented BHS fraction, or parallel-system diversion. The only defensible numeric multiplier is therefore **not yet computable**.

The 1.1/1.25/1.5/2.0 entries published here are non-executable sensitivity descriptors. They are not airport forecasts, task artifacts, runtime results, or demonstrated capacity.

## What the historical input establishes

| Measure | Validated value | Boundary |
| --- | --- | --- |
| Raw bags | 28,506 | bag denominator |
| Processed segments | 43,603 | split legs; not bags |
| Segments per bag | 1.529608 | composition only |
| Early/EBS-split bags | 15,097 (52.961%) | Java rule: STD-entry >= 4,800 s |
| Direct bags | 13,409 | Java rule: STD-entry < 4,800 s |
| 24-hour mean injection | 1187.750 bags/h | not system throughput |
| First / last entry | 8267.845453 / 81503.725820 s | clock-day input |

The seven business loading-station labels exactly reproduce the paper-extracted totals:

| Loader label | Bags |
| --- | --- |
| A1 | 1176 |
| B1 | 2872 |
| B2 | 5544 |
| C1 | 4533 |
| C2 | 7542 |
| D1 | 2585 |
| T | 4254 |

The physical source-node totals differ because several business stations are distributed over multiple map entry nodes:

| Physical source node | Bags |
| --- | --- |
| 0 | 3200 |
| 1 | 3193 |
| 2 | 3199 |
| 3 | 4887 |
| 4 | 4887 |
| 5 | 4886 |
| 53 | 4254 |

This distinction is retained in every future drift audit.

## Time-of-day intensity

| Window | Maximum bags | Equivalent bags/hour | Window start (s) |
| --- | --- | --- | --- |
| 5_minutes | 321 | 3852.000 | 23828.572410 |
| 15_minutes | 847 | 3388.000 | 22631.218210 |
| 60_minutes | 3159 | 3159.000 | 20583.856980 |

Rolling windows are half-open `[observed entry, observed entry + window)`. They measure offered injection demand, not departures or completed throughput.

| Clock hour | Bags | Daily share |
| --- | --- | --- |
| 2 | 22 | 0.077% |
| 3 | 169 | 0.593% |
| 4 | 795 | 2.789% |
| 5 | 2499 | 8.767% |
| 6 | 3107 | 10.899% |
| 7 | 2148 | 7.535% |
| 8 | 1289 | 4.522% |
| 9 | 1338 | 4.694% |
| 10 | 1776 | 6.230% |
| 11 | 1321 | 4.634% |
| 12 | 1467 | 5.146% |
| 13 | 1402 | 4.918% |
| 14 | 1420 | 4.981% |
| 15 | 1442 | 5.059% |
| 16 | 1606 | 5.634% |
| 17 | 1498 | 5.255% |
| 18 | 1859 | 6.521% |
| 19 | 1419 | 4.978% |
| 20 | 1237 | 4.339% |
| 21 | 613 | 2.150% |
| 22 | 79 | 0.277% |

## Deadline, EBS, and route-length composition

- `STD - original_entry_time`: mean=5432.149, p50=4925.863, p95=9794.236, p99=13262.875, min=1215.580, max=14244.165 seconds.
- Planned early-bag interval before Java storage-out release (`STD - 2700 - entry`): mean=4233.812, p50=3424.518, p95=9220.141, p99=10723.945, min=2100.528, max=11544.165 seconds.
- Bag-level directed shortest-path length lower bound: mean=496.491, p50=485.000, p95=590.000, p99=593.000, min=440.000, max=593.000 map units.
- Bag-level directed edge-travel-time lower bound: mean=198.597, p50=194.000, p95=236.000, p99=237.200, min=176.000, max=237.200 seconds.
- Bag-level directed hop lower bound: mean=11.426, p50=12.000, p95=16.000, p99=16.000, min=7.000, max=16.000 edges.

Route values are edge-only static lower bounds summed across a bag's one or two segments. They are not realized routes, conflict-free schedules, queueing times, or THT.

## Airport-scope investigation and claim boundary

The local thesis evidence reports a real international-airport terminal case in southwest China, 24 hours, seven loading stations, one EBS, and 28,506 bags. It does not name the airport or terminal. The fixed topology and demand fields do not distinguish Chengdu from Chongqing.

CAAC's official 2019 table reports whole-airport passenger movements of 55,858,552 for Chengdu Shuangliu and 44,786,722 for Chongqing Jiangbei ([CAAC source](https://www.caac.gov.cn/XXGK/XXGK/TJSJ/202003/t20200309_201358.html)). Those totals are context only: passenger movements include arrivals and departures and say nothing about terminal allocation, checked-bag propensity, transfer flows, the represented subsystem, or parallel BHS diversion.

| Candidate context | Unsupported illustration | Calibration role |
| --- | --- | --- |
| Chengdu Shuangliu 2019 | 0.37254 bags/departing passenger if 50% departures and 100% system share | NONE |
| Chongqing Jiangbei 2019 | 0.46463 bags/departing passenger under the same unsupported assumptions | NONE |

These two ratios are counterexamples to direct annual-throughput mapping, not estimates. Neither assumption set is admitted into the calibration.

## Fail-closed multiplier

`multiplier = represented-system design-day checked bags / 28,506`

The represented-system numerator requires case-period annual passengers, design-day factor, departure share, terminal allocation, local/transfer shares and checked-bag rates, represented-subsystem share, and parallel diversion. The design-day EBS share and flight-bank profile constrain composition and time shape. All remain null unless supported by case-specific evidence.

ACRP's official design-day guidance uses flight-by-flight schedules and airport-specific time-of-day/facility profiles ([ACRP Research Report 163](https://nap.nationalacademies.org/read/23692/chapter/9)). IATA's official planning material likewise treats peak forecasting, design-day schedules, demand-capacity calculations, BHS, and bottleneck subsystems explicitly ([ADRM](https://www.iata.org/en/publications/manuals/airport-development-reference-manual/), [Demand Triggers](https://www.iata.org/contentassets/d1d4d535bf1c4ba695f43e9beff8294f/demand-triggers-for-airport-investments.pdf)).

## Provisional sensitivity descriptors

| Nominal x | Label | Arithmetic bag count | Calibration | Execution |
| --- | --- | --- | --- | --- |
| 1.0 | historical_observed_day_reference | 28506 | HISTORICAL_OBSERVED_DAY_REFERENCE | BLOCKED_NOT_RUN |
| 1.1 | mild_growth_sensitivity | 31357 | UNCALIBRATED_SENSITIVITY_ONLY | BLOCKED_NOT_RUN |
| 1.25 | busy_day_sensitivity_not_calibrated | 35633 | UNCALIBRATED_SENSITIVITY_ONLY | BLOCKED_NOT_RUN |
| 1.5 | engineering_reserve_sensitivity | 42759 | UNCALIBRATED_SENSITIVITY_ONLY | BLOCKED_NOT_RUN |
| 2.0 | extreme_stress_sensitivity | 57012 | UNCALIBRATED_SENSITIVITY_ONLY | BLOCKED_NOT_RUN |

1.25x is not asserted to be a standard design-day factor or a realistic peak. It is a requested provisional sensitivity between mild growth and engineering reserve. All descriptor counts use decimal `ROUND_HALF_UP`; no workload was generated.

## Capacity protocol

A future capacity frontier must report offered injections at 5/15/60-minute and source/loader resolution, critical edge/corridor/merge busy-time utilization, original-entry p95/p99 tails, deadline misses, separate source and in-network backlog, post-peak drain-to-zero time, service level, and unresolved deadlocks. A run is not stable merely because it terminates.

MAPF/MAPD literature is useful only for auxiliary diagnostics here. MAPD models online task arrivals ([AAMAS 2017](https://www.ifaamas.org/Proceedings/aamas2017/pdfs/p837.pdf)); lifelong MAPF defines time-based throughput and reports map-specific density effects ([AAAI 2021](https://ojs.aaai.org/index.php/AAAI/article/view/17344)). Therefore active agents per node may characterize a particular closed-loop run, but cannot replace airport demand calibration.

## Phase-L gate

`BLOCKED_NOT_RUN`: no G4IRSF12-J full 1x formal PASS/mean-target evidence exists; the numeric demand multiplier is unknown; and the 1.1 manifest is a descriptor rather than a materialized traceable workload. The protected map identity does pass.

No scale runtime was started.
