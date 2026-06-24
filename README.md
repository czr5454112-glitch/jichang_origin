# czr005

JunctionShield-MARL for airport Individual Carrier System baggage routing.

This repository starts from the legacy Java/Eclipse ICS simulator and builds a faithful headless research stack:

```text
legacy Java reference
  -> Python reference parser/simulator
  -> C++ high-performance core
  -> Python learning environment
  -> shielded decentralized policies
```

Current scope:

- Phase0/Phase1 legacy source fixation, map/task parsing, Python reference simulator, C++ core smoke parity, `czr005.cpp_backend` build-tree loading, and explicit Java-compatible parsing for the ragged `example1/map.txt` heuristic fixture with Python/C++ A* parity.
- Phase2 non-learning baselines: A*, reservation/SIPP, rolling-horizon SIPP, route-discarding periodic SIPP replanning with static/repair-window faults, explicit buffer-capacity and merge-group shield checks, PIBT-style shield with bounded recursive handoff, active-bag PIBT replay parity, and active-bag/replan-cost diagnostics.
- Phase8 native C++ event replay with Python/C++ parity over persisted synthetic schedules and real legacy `map2/inputdata` windows, including repair windows plus explicit buffer-capacity and merge-group configurations where configured.
- Phase9 early runtime scaling, matched baseline-comparison, heldout-like synthetic matched diagnostics, dense active-bag PIBT stress sweeps, randomized-topology/task-source PIBT stress and all-family matched sweeps, repeated matched-family timing with local hardware metadata/95% CIs, and unified evidence diagnostics compare Python/native C++ throughput while surfacing existing Phase2/Phase5/Phase8 baseline evidence in one table.
- Learning experiments are still smoke/prototype scope, not final paper-grade RL results.
- Legacy Java files are read-only reference material.

## Quick Start

```powershell
conda env create -f environment.yml
conda activate czr005
python scripts/convert_legacy/convert_map2.py
python scripts/convert_legacy/convert_inputdata.py
python -m pytest
```

## Legacy Source

The Java reference project is expected at:

```text
legacy/jichang_origin_readonly
```

It is copied from `jichang_origin` and should not be modified in this repository.
