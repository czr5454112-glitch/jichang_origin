"""Archive source-only candidate and its completed pure evidence; no native API."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

from scripts.experiments.g31_ics_circulation import route_update_pending_ack as candidate
from scripts.experiments.g31_ics_circulation import replay_route_pending_ack as replay

ref=candidate.reference
root=ref.ROOT
out=ref.OUT
folder=out/"route_pending_ack_source_001"
assert not folder.exists()
folder.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=out/"original_route_internal_deadline_prepare_001"
plan=ref.old.read(old/"preregistered_protocol.json")
ref.verify_pins(old,plan)
report_path=out/"route_pending_ack_saved_replay_001.json"
report=ref.old.read(report_path)
assert report["native_executions"]==0
for path,digest in report["source_sha256"].items():assert sha(path)==digest
test=root/"tests/test_g31_circulation_route_pending_ack.py"
xml=out/"route_pending_ack_pure_002.xml"
suites=ET.parse(xml).getroot().findall("testsuite")
counts={key:sum(int(s.attrib[key]) for s in suites) for key in ("tests","failures","errors","skipped")}
assert counts=={"tests":39,"failures":0,"errors":0,"skipped":0}
sources=set(ref.source_paths())|{Path(candidate.__file__).resolve(),Path(replay.__file__).resolve(),test,Path(__file__).resolve()}
pins={}
for path in sorted(sources):
    dest=folder/"source_archive"/path.relative_to(root)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,dest)
    pins[str(path)]={"sha256":sha(path),"archive":str(dest)}
    assert sha(path)==sha(dest)
contract={
    "scope":"Finite witnessed-case first-hop update only. Same root admitted before first fresh view at9600; no production integration and no long-term route-maintenance claim.",
    "arm_guard":"Only the same instance's unchanged public-view path can transition edge=None to real observed first-hop proof; reservation alone is insufficient. Eligibility wake must already have fired. Pin immutable decision and observed evidence hashes.",
    "omission":"After proof, omit only request-side observe_protocol calls; never synthesize an observation or update last_now/observation_count/reservation. Refresh real ProtocolClient queries and immutable retries on every original activation.",
    "closure":"Original delivered terminal ACK rules, actual hop/wrong-hop evidence, same root retry lineage, mandatory complete native drain and JSON response encoding remain required. Missing ACK stays open even after actual hop.",
    "changed_diagnostics":["intent.observation_count","intent.last_now","intent.reservation","those three fields inside encoded returned response","new pending_ack_path diagnostics"],
    "future_actual_gates":[
        "Same accepted binary/input/case faults; baseline0,drop_first_ack1,ack_withheld_in_window100. Same28506jobs/22trays/R1 research authorization/2s wire/60s retry/H9900/shared600 envelope.",
        "Exact prefix through observed-hop proof and unchanged root admission; ordered request APIs exact after deleting only the candidate-declared postproof request observe_protocol calls from reference.",
        "Exact immutable submissions/retries/delivered queries, observed-hop evidence, terminal/open outcome, mandatory drain, all remaining semantic response fields and client outbox.",
        "All background controller calls/states/native boundaries and final complete H9900 result+native seal must match. Read omission must not change source/receiver physical state or scheduling.",
        "Keep each actual measured warm/cold bound, child/campaign setup and all diagnostic costs. Read-omission counts alone do not predict speedup or prove100ms."
    ],
    "pure_replay_limit":"Saved native replies and old clocks test request-side conformance only; native physical equivalence, common-H candidate seal and candidate runtime remain unmeasured."
}
receipt={
    "schema":"g31.pending_ack.source_only.v1","status":"source_and_pure_evidence_ready_for_review",
    "source_pins":pins,"source_count":len(pins),"reference_plan":{"path":str(old/"preregistered_protocol.json"),"sha256":sha(old/"preregistered_protocol.json")},
    "pure_tests":{"path":str(xml),"sha256":sha(xml),**counts},
    "actual_saved_request_replay":{"path":str(report_path),"sha256":sha(report_path),"cases":{name:{key:row[key] for key in ("closed","reference_request_rows","candidate_request_rows","omitted_full_observations")} for name,row in report["cases"].items()}},
    "ast_proof":candidate.prove_unchanged_closure_tail(),"comparison_contract":contract,
    "native_executions":0,"native_equivalence_proved":False,"runtime_speedup_measured":False,"complete_100ms_certified":False
}
for path,row in pins.items():assert sha(path)==row["sha256"]==sha(row["archive"])
ref.verify_pins(old,plan)
target=folder/"source_plan.json"
ref.old.write(target,receipt)
print(json.dumps({"path":str(target),"sha256":sha(target),"source_count":len(pins),"tests":counts}))
