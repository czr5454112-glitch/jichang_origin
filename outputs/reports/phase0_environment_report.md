# Phase0 Environment Report

Date: 2026-06-24

## Conda

Environment name:

```text
czr005
```

Environment path:

```text
C:\Users\38908\.conda\envs\czr005
```

`conda env list` recognizes the environment.

## Verified Commands

```text
C:\Users\38908\.conda\envs\czr005\python.exe --version
Python 3.11.15
```

```text
C:\Users\38908\.conda\envs\czr005\python.exe -c "import numpy; print(numpy.__version__)"
2.4.6
```

```text
C:\Users\38908\.conda\envs\czr005\python.exe -m pytest --version
pytest 9.0.3
```

```text
C:\Users\38908\.conda\envs\czr005\Library\bin\cmake.exe --version
cmake version 4.3.3
```

```text
C:\Users\38908\.conda\envs\czr005\python.exe -c "import pybind11; print(pybind11.__version__)"
3.0.3
```

```text
cmake --build C:\PROGRAMING\czr005\build_vs --config Debug
build passed; czr005_cpp.cp311-win_amd64.pyd and test_cpp_core_smoke.exe were produced
```

```text
ctest --test-dir C:\PROGRAMING\czr005\build_vs -C Debug --output-on-failure
2/2 tests passed
```

```text
C:\Users\38908\.conda\envs\czr005\python.exe -m pytest tests/test_cpp_binding_smoke.py tests/test_cpp_backend.py tests/test_legacy_parsers.py tests/test_phase1b_sim_py.py tests/test_phase2_baselines.py -q
42 passed
```

## Notes

The full `environment.yml` solve/install attempt timed out once during the initial setup. The registered `czr005` environment now satisfies the Phase0/Phase1 prerequisites used by this repository: Python 3.11, numpy, pytest, CMake, pybind11, Visual Studio C++ activation, C++ build, CTest, and direct pybind smoke have all been verified in later runs.
