"""Owned120 synthetic initial-scope full96 adapter checks, no real model/native."""
from __future__ import annotations
import time
BOOT=time.monotonic()
from . import run_live_communication_scoped_inputs_pure as frozen
from . import validate_live_communication_initial_scoped_inputs as gate

MODULE='scripts.experiments.g31_ics_circulation.run_live_communication_initial_scoped_inputs_pure'
TEST=gate.TEST


def main():
    return gate.private(frozen.main,{'BOOT':BOOT,'MODULE':MODULE,'TEST':TEST,'gate':gate})()


if __name__=='__main__':raise SystemExit(main())
