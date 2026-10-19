"""Owned120 synthetic whole-component ABBA wiring; no actual model/native."""
from __future__ import annotations
import time
BOOT=time.monotonic()
from types import FunctionType
from . import run_scoped_public_inputs_v2_cost_pure as frozen

MODULE='scripts.experiments.g31_ics_circulation.run_initial_scoped_inputs_cost_pure'
TEST='tests/test_g31_circulation_initial_scoped_inputs_cost.py'
COUNT=30


def main():
    function=FunctionType(frozen.main.__code__,{**frozen.main.__globals__,
        'BOOT':BOOT,'MODULE':MODULE,'TEST':TEST,'COUNT':COUNT},frozen.main.__name__,
        frozen.main.__defaults__,frozen.main.__closure__)
    function.__kwdefaults__=frozen.main.__kwdefaults__
    return function()


if __name__=='__main__':raise SystemExit(main())
