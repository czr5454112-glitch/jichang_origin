# G4IRSF11 CI or blocker report

Local validation-command status: `BLOCKED`.
Production Gate-A status: `FAIL`.

## Exact target test list

- `tests/test_g4irsf11_gate_integrity.py`
- `tests/test_g4irsf11_provenance_audit.py`
- `tests/test_g4irsf11_g4irsf10_audit.py`

## Executed commands and return codes

| Executable command | Return code |
| --- | --- |
| C:\Users\38908\.conda\envs\czr005\python.exe -m py_compile scripts/eval/g4irsf11_fixed_map.py scripts/eval/g4irsf11_gate_integrity.py scripts/eval/g4irsf11_provenance_audit.py scripts/eval/g4irsf11_g4irsf10_audit.py scripts/eval/run_g4irsf11_gate_a_production_audit.py | 0 |
| C:\Users\38908\.conda\envs\czr005\python.exe -m pytest -q tests/test_g4irsf11_gate_integrity.py tests/test_g4irsf11_provenance_audit.py tests/test_g4irsf11_g4irsf10_audit.py --basetemp C:\PROGRAMING\czr005\.pytest_cache\g4irsf11\gate_a_production.pending-549f1fd69e2a46ba9a2609a11885d80e_tests | 0 |
| C:\Users\38908\.conda\envs\czr005\python.exe scripts/eval/validate_g4irsf11_committed_artifacts.py | 2 |
| C:\Users\38908\.conda\envs\czr005\python.exe scripts/eval/g4irsf11_gate_integrity.py --repo C:\PROGRAMING\czr005 --config C:\PROGRAMING\czr005\artifacts\gates\g4irsf11_gate_a_production_config.json --output C:\PROGRAMING\czr005\.pytest_cache\g4irsf11\gate_a_production.pending-549f1fd69e2a46ba9a2609a11885d80e.json | 2 |

The production gate command is expected to return `2` while evidence blockers remain; that non-zero code is recorded rather than relabelled as a test failure or PASS.

## Promotion blockers

- `paper_scenario_exact_set_hash_status`
- `optional_executed_or_explicit_blocker`
- `hard_case_stratified_coverage_and_validity`

Raw local gate JSON: `.pytest_cache/g4irsf11/gate_a_production.json` (ignored runtime evidence).
Committed config: `artifacts/gates/g4irsf11_gate_a_production_config.json`.
