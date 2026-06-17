# Phase3 Learning Environment Smoke Report

Date: 2026-06-17

## Scope

This smoke validates the first Python junction-decision learning environment. The environment exposes reset/step, candidate-edge observations, action masks, reward shaping, hard shield fallback, and structured episode summaries without depending on Gymnasium or PettingZoo yet.

## Metrics

| Policy | Max tasks | Planned | Unplanned | Steps | Post-shield conflicts | Shield blocks | Unsafe proposals | Mean travel | P95 travel | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astar_guided_safe | 8 | 8 | 0 | 78 | 0 | 0 | 0 | 49.750000 | 55.390000 | 0.046773 |
| random_safe | 16 | 16 | 0 | 429 | 0 | 0 | 0 | 169.162500 | 361.200000 | 0.173738 |

CSV: `outputs/tables/phase3_learning_env_smoke_metrics.csv`

## Gate Status

- reset/step API: PASS
- shortest-path safe policy runs: PASS
- random safe policy runs: PASS
- post-shield conflicts: PASS
- episode logs complete: PASS

## Remaining Work

- PettingZoo-compatible multi-agent wrapper or custom batched decision dataset
- richer local occupancy, merge-group occupancy, and buffer-occupancy features
- queue-aware scripted policy baseline inside the environment
- teacher slice export for imitation learning
