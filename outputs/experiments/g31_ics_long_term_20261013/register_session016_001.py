"""Bind actual evidence to its version, preserve failures, and register local results."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).absolute().parents[3]
E=ROOT/"outputs/experiments/g31_ics_long_term_20261013"
D=ROOT/"docs/g31_ics_circulation"
OUT=E/"session016_handoff_integrity_001.json"
assert not OUT.exists(), "Use a new receipt; never overwrite prior integrity evidence"

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def git(cwd,*args):
    return subprocess.run(["git",*args],cwd=cwd,capture_output=True,check=True).stdout.decode("utf-8").strip()

checks={}
receipts={}
for label,folder in [
    ("build016","p1_build_016"),("live012","live_validation_012"),
    ("checkpoint009_compiled_sources","p1_checkpoint_validation_009"),
    ("legacy005_compiled_sources","legacy_parity_005"),
    ("original_five_policies016","event_protocol_original24_016_001")]:
    r=read(E/folder/"receipt.json"); receipts[label]=r
    before=r["source_before"]
    mismatch=[p for p,h in before.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    assert not mismatch,(label,mismatch)
    assert not r.get("source_changed"),label
    assert r["status"] in ("passed","executed_comparison_not_research_gate"),(label,r["status"])
    checks[label]=dict(files=len(before),mismatches=mismatch,receipt_sha256=sha(E/folder/"receipt.json"))
binary=ROOT/"build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd"
assert sha(binary)=="af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0"
v=receipts["live012"]
assert v["counts"]==dict(tests=407,failures=0,errors=0,skipped=0)
assert v["current_native_and_python_test_count"]==401
assert v["historical_order_regression"]["test_count"]==1
assert v["native_identity_regression"]["test_count"]==5
assert sha(binary)==v["binary_sha256"] and sha(binary) in receipts["build016"]["binary_sha256"].values()
assert read(E/"event_protocol_015_016_comparison_001/assessment.json")["status"]=="passed"
protected=ROOT.parent/"cpp/ics_core/runtime/bounded_local_pibt.hpp"
assert sha(protected)=="b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"
states={}
for label,p in [("circulation",ROOT),("user_original",ROOT.parent)]:
    assert not git(p,"diff","--cached","--name-only")
    states[label]=dict(branch=git(p,"branch","--show-current"),head=git(p,"rev-parse","HEAD"),staged=[])
assert states["circulation"]["head"]=="46cc46ab6bc121628fd6357e9f3c7636745fd732"
assert states["user_original"]["head"]=="fccd4819532701ee4173ec598822450d962d4e61"
historical_context={}
for folder in ["p5_handoff_011_003","p5_handoff_015_001","p5_dependency_repair_015_001"]:
    r=read(E/folder/"receipt.json")
    mismatch=[p for p,h in r.get("source_before",{}).items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    historical_context[folder]=dict(current_source_differences=mismatch,
        scope="Preserved version-bound actual experiment; not a claim that all its archived Python sources are still current.")
integrity=dict(schema="g31.session016_handoff_integrity.v1",status="passed",binary_sha256=sha(binary),
    source_identity_checks=checks,historical_experiment_context=historical_context,
    git_states=states,protected_file=str(protected),protected_file_sha256=sha(protected),
    regression_counts=v["counts"],regression_scope=dict(current_native_and_python=401,historical011=1,identity011_015=5),
    committed=False,pushed=False,
    scope="Current source/binary/receipts and protected user state identity check; not an extra simulation, paper result or publication.")
OUT.write_text(json.dumps(integrity,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

prefixes=("adjacent_float_before_013","event_control_","event_notification_","event_protocol_",
    "owner_notification_","original_protocol_24_forecast_diagnosis_","native_identity_","p5_handoff_",
    "p5_dependency_order_","session016_final_review_")
folders=[p for p in E.iterdir() if p.is_dir() and (
    p.name.startswith(prefixes) or p.name in {
    "p1_build_012","p1_build_013","p1_build_014","p1_build_015","p1_build_016",
    "p1_checkpoint_validation_008","p1_checkpoint_validation_009","legacy_parity_005",
    "live_validation_010","live_validation_011","live_validation_012",
    "p5_dependency_repair_011_001","p5_dependency_repair_015_001","protocol_serialization_tests_016_001"})]
names={"receipt.json","execution_receipt.json","assessment.json","comparison.json",
    "prepared_not_executed.json","result.json","source_identity.json","diagnosis.json",
    "interpretation.json","existing_run_breakdown.json","cross_version.json","fresh_011.json","fresh_015.json","final.json"}
selected=[p for folder in folders for p in folder.iterdir() if p.is_file() and p.name in names]
selected += [p for folder in folders for p in folder.glob("*.xml")]
selected += [p for p in E.glob("*.xml") if p.name.startswith(("event_control","p5_handoff","p5_dependency_order"))]
selected += [p for p in E.glob("event_notification_time_probe_*.json")]
selected += [E/"event_control_readonly_profile_015_001/raw/receipt.json",OUT]
selected=sorted(set(selected))
index=D/"RESULT_INDEX.jsonl"
existing=[json.loads(line) for line in index.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
known={r["id"]:r for r in existing}
new=[]
for p in selected:
    assert p.is_file(),p
    identity="LT-RAW-"+p.relative_to(E).as_posix()
    if identity in known:
        assert known[identity]["artifact_sha256"]==sha(p),identity
        continue
    if p.suffix==".xml":
        cases=ET.parse(p).findall(".//testcase")
        counts=dict(tests=len(cases),failures=sum(c.find("failure") is not None for c in cases),
            errors=sum(c.find("error") is not None for c in cases),skipped=sum(c.find("skipped") is not None for c in cases))
        obj=dict(status="failed" if counts["failures"] or counts["errors"] else "passed",counts=counts)
    else:
        obj=read(p)
        if not isinstance(obj,dict):obj={}
    record=dict(id=identity,artifacts=p.relative_to(ROOT).as_posix(),artifact_sha256=sha(p),
        recorded_status=obj.get("status","recorded; inspect actual case outcomes"),source_changed=obj.get("source_changed"),
        binary_sha256=obj.get("binary_sha256"),independent_source=False,
        scope="Version-bound local evidence. Includes failed, truncated, historical, preparation-only and read-only audit records. Tests overlap; no summed novelty/global-optimality/full100ms certification.")
    if "counts" in obj:record["counts"]=obj["counts"]
    if p.name=="prepared_not_executed.json":record["recorded_status"]="prepared_not_executed"
    if p.parent.name=="live_validation_011":record["scope"] += " One original scope sentence was overbroad about identity tests; corrected and rerun in live_validation_012."
    if p.parent.name in ["live_validation_011","live_validation_012"]:
        record["test_scope"]="407=401 current native/Python +1 retained011 witness +5 pinned011/015 identity; not407 current physical tests."
    new.append(record)
with index.open("a",encoding="utf-8",newline="\n") as stream:
    for record in new:stream.write(json.dumps(record,ensure_ascii=False)+"\n")
s=read(D/"RESEARCH_STATE.json")
s["new_result_registration"]=dict(script=Path(__file__).relative_to(ROOT).as_posix(),
    added_raw_entries=len(new),total_index_entries=len(existing)+len(new),
    integrity_receipt=OUT.relative_to(ROOT).as_posix())
for p in selected:
    if p.suffix==".json" and isinstance(read(p),dict) and read(p).get("status") in (
        "passed","executed_comparison_not_research_gate","executed_finite_diagnostic","executed","equivalent"):
        rel=p.relative_to(E).as_posix()
        if rel not in s["verified_artifacts"]:s["verified_artifacts"].append(rel)
(D/"RESEARCH_STATE.json").write_text(json.dumps(s,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps(dict(status="registered",new_entries=len(new),total_entries=len(existing)+len(new),
    source_checks=checks,git_states=states),ensure_ascii=False))

