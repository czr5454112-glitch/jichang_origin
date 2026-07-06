# CZR005 No-A* Streaming Runtime API

## API

`czr005.cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(...)` binds to the C++ pybind entry `g4irsf4_no_astar_streaming_replay_from_jsonl`.

The API accepts graph records, the JSONL task path, policy weights, risk thresholds, optional fault edges/windows, and summary/profile flags. C++ reads the JSONL path and builds one continuous full-manifest replay window named `full_manifest_348824_continuous_state`.

`reservation_semantics` is optional and defaults to `baseline`, preserving the G4IRSF4-G4IRSF6 closed-boundary node reservation behavior. G4IRSF7 uses explicit engineering diagnostics such as `reservation_open_end_boundary` and `source_node_no_reservation` to test Java/source-release alignment without changing the default replay path.

## Boundary

- It does not pass a 348824-row Python route list through pybind.
- It keeps node reservations, traffic memory, edge diagnostics, and policy counters inside one C++ replay call.
- It does not call runtime full CIE/A*.
- It does not use teacher path, teacher next, future schedule, or route suffix leakage.
- It does not modify legacy Java or the real map.

## State Schema

See `outputs/tables/g4irsf4_runtime_state_schema.csv`.
