# Implementation Notes

## Legacy Boundary

The Java/Eclipse simulator is treated as a read-only reference. The GUI, direct file writes, and static execution loop are not used as the learning interface.

The first faithful port boundary is data-level:

- `map2.txt` is parsed into a typed directed graph schema.
- `inputdata.txt` is expanded with the same early-bag split rule used by `RUN.Main.ReadTaskList`.
- Generated outputs are JSON/JSONL and are deterministic.

## Current Phase

Phase1A implements legacy parsers only. Phase1B adds a headless Python reference simulator with:

- typed graph loading,
- expanded task stream loading,
- Java-compatible node reservation intervals,
- legacy-style A* route planning,
- structured episode replay logs,
- shared episode metrics.

It intentionally avoids:

- reinforcement learning code,
- Gym/PettingZoo environments,
- policy models,
- changes to legacy Java files.

## Next Port Steps

1. Build a headless Python reference simulator around the parsed graph/task stream.
2. Implement the C++ graph/task/event/reservation primitives.
3. Add parity tests that compare Python and C++ outputs on the same fixtures.
