# Phase1A Legacy Schema Report

Date: 2026-06-16

## Inputs

- Legacy map: `legacy/jichang_origin_readonly/map2.txt`
- Legacy task stream: `legacy/jichang_origin_readonly/inputdata.txt`
- Java reference logic:
  - `src/App/Map.java`
  - `src/RUN/Main.java`

## Map Schema

`map2.txt` is parsed as:

1. Header: `node_count agv_length safe_length fault_threshold`.
2. `node_count` node rows: `location type service_time y x outgoing...`.
3. `node_count` heuristic rows.
4. Directed edge rows: `start end length [speed]`.

The Java reference divides heuristic values and edge lengths by fixed speed `2.5` for time-cost semantics. The legacy edge rows contain a fourth `2.5` column, but Java ignores that field and sets edge speed internally.

Expected fixed counts:

| Item | Count |
|---|---:|
| Nodes | 54 |
| Heuristic rows | 54 |
| Directed edges | 69 |

Node type counts:

| Type | Count |
|---|---:|
| 1 | 8 |
| 2 | 5 |
| 4 | 19 |
| 5 | 22 |

## Task Schema

`inputdata.txt` is parsed as:

```text
ID EntryTime(s) STD(s) star end Unloader Loader
```

The Java reference skips the header, then expands each row with this rule:

- If `STD - EntryTime < 4800`, create one direct task leg from `star` to `end`.
- Otherwise create two legs:
  - original `star` to storage node `47` at original entry time,
  - storage release from node `52` to original `end` at `STD - 2700`.

Expected fixed counts:

| Item | Count |
|---|---:|
| Raw task rows | 28,506 |
| Direct task rows | 13,409 |
| Early-bag raw rows | 15,097 |
| Expanded task legs | 43,603 |

## Outputs

- `data/processed/maps/map2.json`
- `data/processed/tasks/inputdata.jsonl`
- `data/processed/tasks/inputdata_summary.json`

## Gate Status

- Node count equal: covered by tests.
- Edge count equal: covered by tests.
- Source/end nodes equal: covered by tests.
- Heuristic table parsed: covered by tests.
- Task count equal: covered by tests.
- Early-bag split rule matched: covered by tests.
