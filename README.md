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

- Phase0 project hygiene and legacy source fixation.
- Phase1A legacy `map2.txt` and `inputdata.txt` parsing.
- No reinforcement learning code in this round.
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

