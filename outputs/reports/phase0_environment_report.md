# Phase0 Environment Report

Date: 2026-06-16

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
C:\Users\38908\.conda\envs\czr005\python.exe -m pytest
3 passed
```

## Notes

The full `environment.yml` solve/install attempt timed out once after about 10 minutes. The environment is nevertheless registered and satisfies the current Phase0/Phase1A gates. Before C++ binding work, rerun dependency completion or explicitly verify `pybind11`, compiler activation, and build tooling.
