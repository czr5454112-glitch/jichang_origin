"""Explicit025 endpoint envelopes; constructor requires a pinned native module."""
from pathlib import Path

from .capture_native_request_timing import RecentNativeTimingCapture
from .native025_request_timing import ENDPOINTS025, verify_contract


class Native025TimingCapture(RecentNativeTimingCapture):
    def __init__(self, session, *, native_module, contract_reference, acceptance_probe=False, **kwargs):
        verified = verify_contract(contract_reference, require_runtime=not acceptance_probe)
        binary = Path(verified["contract"]["binary"])
        if (getattr(native_module, "NativeSession", None) is not type(session) or
            Path(native_module.__file__).resolve() != binary.resolve()):
            raise ValueError("native025_timing:session_module_identity_mismatch")
        self.contract_reference = dict(contract_reference)
        self.acceptance_probe = acceptance_probe
        super().__init__(session, **kwargs)

    def _invoke(self, name, method, *args, **kwargs):
        if name not in ENDPOINTS025:
            raise ValueError("native025_timing:unclassified_endpoint")
        before = len(self.envelopes)
        bridge = "protocol_planning_snapshots" if name == "protocol_planning_snapshots_v2" else name
        try:
            return super()._invoke(bridge, method, *args, **kwargs)
        finally:
            if len(self.envelopes) == before + 1:
                self.envelopes[-1]["api_endpoint"] = name

    def protocol_planning_snapshots_v2(self, owner):
        return self._invoke("protocol_planning_snapshots_v2", self._session.protocol_planning_snapshots_v2, owner)
