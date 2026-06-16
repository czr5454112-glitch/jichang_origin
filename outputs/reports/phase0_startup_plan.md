# Phase0 Startup Plan

Date: 2026-06-16

## Scope

This startup round establishes the repository, environment metadata, documentation discipline, and read-only legacy reference required before any learning work.

## Required Artifacts

- `README.md`
- `environment.yml`
- `.gitignore`
- `pyproject.toml`
- `CMakeLists.txt`
- `docs/codex-worklog.md`
- `docs/implementation-notes.md`
- `docs/safety-spec.md`
- `legacy/jichang_origin_readonly`
- `outputs/reports/phase1_legacy_schema_report.md`

## Legacy Reference

Expected source:

```text
C:\PROGRAMING\czr004\jichang_origin
```

Recorded commit:

```text
c5c2d2cb050f62b5160cdfb6c29895f03af12486
```

Source repo:

```text
https://github.com/czr5454112-glitch/jichang_origin.git
```

The legacy source is copied for reference only. Do not edit it during the Python/C++ port.

## Gate Status

- Git repository: initialized on `main`.
- Conda environment `czr005`: created and registered at `C:\Users\38908\.conda\envs\czr005`.
- `conda activate czr005` / equivalent activation: starts Python 3.11.15.
- CMake availability: `cmake --version` works; env cmake is 4.3.3.
- `python -c "import numpy"` in `czr005`: works; numpy is 2.4.6.
- Legacy source hash recorded: yes.
- Phase1A parser tests: passed in target with the `czr005` Python.

## Environment Note

The first full `conda env create -f environment.yml -y` attempt timed out after about 10 minutes, likely during dependency solving or package download. The partially completed environment is usable and registered by Conda; Phase0 gates for Python 3.11, numpy, pytest, cmake, and target parser tests passed. A later dependency-completion pass may still be useful before Phase1C/pybind work.
