"""Owned120 fake-only v2 full96 adapter gate, no model/native/raw decode."""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType
from . import run_live_communication_scoped_inputs_pure as frozen
from . import validate_live_communication_scoped_inputs_v2 as gate

MODULE = 'scripts.experiments.g31_ics_circulation.run_live_communication_scoped_inputs_v2_pure'
TEST = gate.TEST


def main():
    # Preserve tested owned lifecycle/source archive/XML/exit checks exactly.
    function = FunctionType(frozen.main.__code__, {**frozen.main.__globals__,
        'BOOT': BOOT, 'MODULE': MODULE, 'TEST': TEST, 'gate': gate}, frozen.main.__name__,
        frozen.main.__defaults__, frozen.main.__closure__)
    function.__kwdefaults__ = frozen.main.__kwdefaults__
    return function()


if __name__ == '__main__': raise SystemExit(main())
