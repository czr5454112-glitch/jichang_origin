"""A delivered historical route ACK is not the current installed preference."""
import os

from scripts.experiments.g31_ics_circulation import protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.probe_protocol_route_aba import execute


def test_native_same_stage_route_aba_requires_fresh_a_after_b(tmp_path):
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    receipt = execute(protocol_control, native, tmp_path)
    assert receipt["fixture_valid"], receipt
    assert receipt["fixed"], receipt
