# G4IRSF24 Fresh HCA Race

Status: `FRESH_HCA_CLEAR_WIN`.

All measured arms use 43,603 segments, 28,506 raw bags, no faults, and the exact fresh HCA release trace. All `2` paired repeats pass the business/completion gates; exact repeat-metric consistency is `PASS`.

| Denominator | Arm | Min (min) | P50 | Mean | P95 | P99 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| processed_attempt | HCA | 3.133333 | 3.866667 | 3.945169 | 4.983333 | 5.500000 | 5.950000 |
| java_release | HCA | 3.133333 | 3.916667 | 3.966661 | 5.000000 | 5.533333 | 6.383333 |
| raw_entry | HCA | 3.116848 | 44.647961 | 43.078157 | 125.725553 | 180.574296 | 207.505491 |
| processed_attempt | F2 | 3.133367 | 3.356700 | 3.523286 | 4.120067 | 4.456608 | 7.546733 |
| java_release | F2 | 3.133367 | 3.356700 | 3.523286 | 4.120067 | 4.456608 | 7.546733 |
| raw_entry | F2 | 3.116881 | 43.894168 | 42.634782 | 125.342443 | 180.328092 | 206.758891 |
| processed_attempt | S4 | 3.133367 | 3.356700 | 3.512829 | 4.120067 | 4.233400 | 6.790067 |
| java_release | S4 | 3.133367 | 3.356700 | 3.512829 | 4.120067 | 4.233400 | 6.790067 |
| raw_entry | S4 | 3.116881 | 43.871590 | 42.624325 | 125.282073 | 180.316411 | 206.758891 |

## Decision

- S4 processed-attempt mean improvement versus fresh HCA: `10.959%`.
- S4 processed-attempt p95 improvement: `17.323%`.
- S4 processed-attempt max improvement: `-14.119%`; a negative value is a tail regression.
- `FRESH_HCA_STRICT_WIN`: `PASS`.
- `FRESH_HCA_CLEAR_WIN`: `PASS`.
- `PAPER_TABLE_MEAN_WIN`: `PASS`.
- `PAPER_TABLE_RANGE_WIN`: `FAIL`.

## Protocol and measurement limits

- Inputs: `legacy/jichang_origin_readonly/map2.txt` and `legacy/jichang_origin_readonly/inputdata.txt`; the legacy Java HCA/A*/priority/reservation logic is unchanged. The compatibility patch only records each task's actual release epoch from the external benchmark wrapper.
- Java was compiled on JDK 18 with `javac --release 8`. Reproduce the two independent Java processes with `python scripts/eval/run_g4irsf24_fresh_hca.py run --profile full --output-root build/g4irsf24_fresh_hca_full`.
- Reproduce F2/S4 after the Java release trace exists with `python scripts/eval/run_g4irsf24_native_race.py`; both native arms must receive the same exact release CSV before comparison.
- Exact release alignment count: `43603`.
- Release minus canonical pass: mean `68.272` s, min `-1.000` s, max `1213.000` s.
- Java wall is end-to-end child-process wall; current native wall is core backend-call wall. A strict computational speedup is `NOT_MEASURED` until one common end-to-end timer is used.
- Fresh deadline misses, peak RSS, and HCA CPU are `NOT_MEASURED`.
