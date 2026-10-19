"""Pinned027 preparation capture; regular runtime use remains fail closed."""
from pathlib import Path
from .capture_native_request_timing import RecentNativeTimingCapture
from .native027_request_timing import ENDPOINTS027, verify_contract


class Native027TimingCapture(RecentNativeTimingCapture):
    def __init__(self, session, *, native_module, contract_reference, acceptance_probe=False, **kwargs):
        verified = verify_contract(contract_reference, require_runtime=not acceptance_probe)
        if (getattr(native_module, "NativeSession", None) is not type(session)
                or Path(native_module.__file__).resolve() != Path(verified["contract"]["binary"]).resolve()):
            raise ValueError("native027_timing:session_module_identity_mismatch")
        self.contract_reference, self.acceptance_probe = dict(contract_reference), acceptance_probe
        super().__init__(session, **kwargs)

    def _invoke(self, name, method, *args, **kwargs):
        if name not in ENDPOINTS027: raise ValueError("native027_timing:unclassified_endpoint")
        before = len(self.envelopes)
        bridge = "protocol_planning_snapshots" if name in {"protocol_planning_snapshots_v2", "protocol_planning_snapshots_v3"} else name
        try: return super()._invoke(bridge, method, *args, **kwargs)
        finally:
            if len(self.envelopes) == before + 1: self.envelopes[-1]["api_endpoint"] = name

    def protocol_planning_snapshots_v2(self, owner):
        return self._invoke("protocol_planning_snapshots_v2", self._session.protocol_planning_snapshots_v2, owner)

    def protocol_planning_snapshots_v3(self, owner):
        return self._invoke("protocol_planning_snapshots_v3", self._session.protocol_planning_snapshots_v3, owner)
