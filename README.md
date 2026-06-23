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

- Phase0/Phase1 legacy source fixation, map/task parsing, Python reference simulator, and C++ core smoke parity.
- Phase2 non-learning baselines: A*, reservation/SIPP, rolling-horizon SIPP, route-discarding periodic SIPP replanning with static/repair-window faults, explicit buffer-capacity and merge-group shield checks, PIBT-style shield with bounded recursive handoff, and active-bag/replan-cost diagnostics.
- Phase8 native C++ event replay with Python/C++ parity over persisted synthetic schedules, including repair windows plus explicit buffer-capacity and merge-group configurations.
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
