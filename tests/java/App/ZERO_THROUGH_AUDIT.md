# CIE-DH zero-through state-machine regression

`ZeroThroughAudit.java` is a test-only class. It must be compiled into a separate
directory from the five production Java sources so it does not change the
production class identity.

The Python gate compiles the production program and test harness, runs all
Z1–Z12 cases twice, and compares both JSONL output and every per-bag tick trace:

```powershell
python -m pytest tests/test_feng_cie_dh_microcases.py tests/test_feng_cie_dh_zero_through.py -q --basetemp build/pytest_zero_through_audit
```

Choose a new `--basetemp` path for each retained evidence run; pytest clears an
existing base temporary directory. The September 5 repair used
`build/pytest_feng_zero_through_20260905_v2` and passed all five Python tests.

To produce standalone native evidence after compiling the production sources:

```powershell
python scripts/eval/run_feng_paper_env_cie_dh.py compile --classes-dir build/feng_cie_dh_zero_through_fix_v1
javac --release 8 -encoding UTF-8 -cp build/feng_cie_dh_zero_through_fix_v1 -d build/feng_cie_dh_zero_through_audit tests/java/App/ZeroThroughAudit.java
java -cp 'build/feng_cie_dh_zero_through_audit;build/feng_cie_dh_zero_through_fix_v1' App.ZeroThroughAudit --gate outputs/runtime/zero_through_audit data/processed/maps/nanning_legacy.txt
```

`--reproduce OUTPUT_DIR` runs only the zero-through and positive-through control
fixtures, prints observed results even when the zero-through assertion fails,
and writes their full traces. Use it against the old production classes to
preserve the negative control. The original core is available at commit
`f101c2f6c21bd4a147e060ba09bf95b26b48b50c`; compile its five files into a separate
directory. Do not overwrite a live campaign's production classes.

The captured repair evidence is in
`outputs/runtime/feng_cie_dh_zero_through_repair_v1/microtests/`:

- `old_reproduction.jsonl`: old zero intermediate reaches tick 100 incomplete,
  with 87 intermediate zero-service starts (88 service starts including source
  induction) and state `MOVING_ON_EDGE`; positive control completes at tick 33.
- `old/` and `new/`: complete per-bag tick traces. The repaired zero fixture
  completes at tick 28 after one zero-service start. The real Nanning
  130→57→58 fixture completes at tick 251.
- `old_T1_T10.jsonl` and `new_T1_T10.jsonl`: byte-identical original mechanism
  gates, all passing.
- `new_regression.jsonl` and `new_regression_repeat.jsonl`: all 12 additional
  cases pass; corresponding repeated trace files are byte-identical.
- `verification.json`: byte comparisons and exact production source/class
  identities. The positive-through control trace is identical before/after.
- `pytest.txt`: the two Python test modules pass, including formal timing gates.

Z3/Z4 verify simultaneous follower motion for both two-cell and one-cell
footprints. Z5 verifies deterministic simultaneous junction competition and
FIFO. Z6 retains an expired transfer timer while the downstream edge is
occupied, then completes after release. Z7 prevents a valid finite service
from being declared deadlocked with an idle threshold shorter than the service.
Z8 confirms that repeated unreachable decisions do reach `DEADLOCK`. Z9 checks
the explicit duplicate-boundary-service diagnostic. Z10 separates zero-time
goal completion from intermediate transfer. Z12 verifies that a ready source
can enter the upstream edge in the same commit as the zero-through departure.

The five production files use CRLF in the Windows working tree. The final
correctness source aggregate is
`3b47ffcefa558365e55e27508fc8904608026fd3235102eee6c305539999a208`;
the 33-class aggregate is
`21fc22d8cd27628e2933eb73256cafa6f2bd695628fd46988ea445aafd7a5d47`.
The original source aggregate is
`99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`.
Compiled classes remain local build artifacts and should not be committed.
