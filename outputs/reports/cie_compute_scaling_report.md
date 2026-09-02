# CIE compute-scaling audit

Explicit observations: **17**; identity VERIFIED: **17**.

This is a read-only extraction of already-produced formal JSON. It did not start, rerun, or tune any algorithm.

Wall time, CPU time, RSS, event count and decision count are reported only when the source measured them. `N/M` means not measured and is accompanied by a reason in the CSV. Per-completed-bag values are within-observation descriptive normalizations only.

**Cross-language and cross-executor wall-time multiples are not causal algorithm effects.** Java versus C++/Python-binding runtime includes language, VM, instrumentation, executor, release and coordination differences. These rows cannot establish pure algorithmic complexity or a cross-protocol speedup.

The 2× THT rule is outside this compute table. Survivor/common-cohort use is never inferred: it is copied only from an explicit source field, otherwise `N/M`.

## Observations

| label / configuration | executor/language | release | coordination | map/load | identity | completed bags | wall (s) | CPU (s) | RSS | events | decisions | wall/bag |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| hca_java / FENG_NATIVE_HCA_REGRESSION | FENG_NATIVE_JAVA_HCA_SCHEDULER / JAVA | ORIGINAL_JAVA_TASK_RELEASE | CENTRALIZED_ASTAR_RESERVATION | map2 / 1× | VERIFIED | 28506 | 243.788 | N/M | N/M | N/M | N/M | 0.00855216 |
| g31_native / H_SA | COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE / C++_PYTHON_BINDING | canonical_complete_flight_population | J2_M3_JIT_FAIR_AGING_DEADLINE | map2 / 1.0× | VERIFIED | 28506 | 23.3 | 22.625 | N/M | 3997648 | 336638 | 0.000817373 |
| g31_native / H_SA | COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE / C++_PYTHON_BINDING | canonical_complete_flight_population | J2_M3_JIT_FAIR_AGING_DEADLINE | map2 / 2.0× | VERIFIED | 57012 | 53.295 | 52.0781 | N/M | 8276538 | 672387 | 0.000934802 |
| g31_native / H_SA | COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE / C++_PYTHON_BINDING | canonical_complete_flight_population | J2_M3_JIT_FAIR_AGING_DEADLINE | nanning / 1.0× | VERIFIED | 28506 | 47.7205 | 46.4844 | N/M | 7087605 | 588936 | 0.00167405 |
| g31_native / H_SA | COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE / C++_PYTHON_BINDING | canonical_complete_flight_population | J2_M3_JIT_FAIR_AGING_DEADLINE | nanning / 2.0× | VERIFIED | 57012 | 737.004 | 716.375 | N/M | 15449370 | 1184109 | 0.0129272 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_FREE_FLOW | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | same_hca | neutral_fifo | map2 / 1× | VERIFIED | 28506 | 20.3233 | 19.75 | N/M | 3849779 | 334952 | 0.000712947 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_FREE_FLOW | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | map2 / 2× | VERIFIED | 57012 | 51.0019 | 49.625 | N/M | 8232284 | 673416 | 0.000894582 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_FREE_FLOW | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | same_hca | neutral_fifo | nanning / 1× | VERIFIED | 28506 | 43.0982 | 41.9688 | N/M | 6832927 | 607288 | 0.0015119 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_FREE_FLOW | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | nanning / 2× | VERIFIED | 49158 | 1834.76 | 1777.83 | N/M | 17685267 | 1337061 | 0.0373238 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_SERVICE_AWARE | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | same_hca | neutral_fifo | map2 / 1× | VERIFIED | 28506 | 20.2523 | 19.75 | N/M | 3829878 | 333216 | 0.000710457 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_SERVICE_AWARE | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | map2 / 2× | VERIFIED | 57012 | 49.9762 | 48.7188 | N/M | 8189748 | 669997 | 0.000876591 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_SERVICE_AWARE | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | same_hca | neutral_fifo | nanning / 1× | VERIFIED | 28506 | 39.6805 | 38.2969 | N/M | 6255504 | 551085 | 0.00139201 |
| cie_dh_common_executor / CIE_DH_COMMON_EXECUTOR_SERVICE_AWARE | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | nanning / 2× | VERIFIED | 49038 | 1665.07 | 1615.81 | N/M | 17072608 | 1263794 | 0.0339546 |
| tarau_common_executor / TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | map2 / 1× | VERIFIED | 28506 | 24.2088 | 23.6562 | N/M | 4061624 | 340668 | 0.000849253 |
| tarau_common_executor / TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | map2 / 2× | VERIFIED | 57012 | 56.6026 | 55.6094 | N/M | 8476044 | 683767 | 0.000992818 |
| tarau_common_executor / TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | nanning / 1× | VERIFIED | 28506 | 73.0992 | 71.8906 | N/M | 8605281 | 692374 | 0.00256434 |
| tarau_common_executor / TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT | COMMON_CPP_EVENT_EXECUTOR / C++_PYTHON_BINDING | canonical | neutral_fifo | nanning / 2× | VERIFIED | 47707 | 1473.02 | 1442.23 | N/M | 16790794 | 1278494 | 0.0308763 |

No cross-row ratios, asymptotic exponents, or survivor-derived performance values are produced.
