import ast
import copy
import json
import pickle
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import native027_run_acceptance as admission
from scripts.experiments.g31_ics_circulation import native_preexisting_v3_run_adapter as adapter
from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3_run as runner
from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3 as original


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source, raw = tmp_path / "source.py", tmp_path / "raw.json"
    source.write_text("immutable source\n")
    raw.write_text('{"status":"captured"}\n')
    pins = {str(p): admission.sha(p) for p in (source, raw)}
    refs = [{"path": str(tmp_path / name), "sha256": name} for name in ("contract", "semantic", "campaign")]
    Path(refs[2]["path"]).write_text(json.dumps({"rows": {key: {"case": key, "method": "fixed", "fault": None} for key in ("a", "b", "c")}}))
    refs[2]["sha256"] = admission.sha(refs[2]["path"])
    verified = {"reference": refs[0], "runtime_accepted": True,
                "contract": {"binary_sha256": "binary", "runtime_acceptance": refs[1], "binary": str(source)}}
    semantic = {"status": "validated_native027_finite_semantic_regression", "passed": 21}
    calls = []
    monkeypatch.setattr(admission, "inventory", lambda *a: dict(pins))
    monkeypatch.setattr(admission.timing, "verify_contract", lambda *a, **k: calls.append("44") or copy.deepcopy(verified))
    monkeypatch.setattr(admission.semantic, "verify_saved_semantic_gate", lambda *a, **k: calls.append("21") or copy.deepcopy(semantic))
    return SimpleNamespace(refs=refs, pins=pins, source=source, raw=raw, calls=calls,
                           verified=verified, semantic=semantic, open=lambda: admission.open_run(*refs))


def test_only_factory_and_nonserializable_process_capability(setup):
    with pytest.raises(ValueError, match="closed_factory"):
        admission.RunAcceptance(object(), *setup.refs, setup.pins, setup.verified, setup.semantic, [], {})
    run = setup.open()
    with pytest.raises(TypeError, match="not_serializable"):
        pickle.dumps(run)
    assert not adapter.is_native_collected({"native_delivery_verified": True})
    assert run.close()["status"] == "closed_run_acceptance_passed"


def test_full_verifiers_only_entry_exit_but_every_branch_hashes(setup):
    run = setup.open()
    for key in ("a", "b", "c"):
        run.enter_branch(key, setup.refs[2])
        assert run.active_for(key)
        assert run.contract_copy(key) == setup.verified
        run.finish_branch(key)
        assert not run.active_for(key)
    assert setup.calls == ["44", "21"]
    final = run.close()
    assert setup.calls == ["44", "21", "44", "21"]
    assert final["status"] == "closed_run_acceptance_passed" and not final["active"]
    assert len([r for r in final["costs"] if r["phase"].startswith("branch_")]) == 6
    with pytest.raises(ValueError, match="already_closed"):
        run.close()
    with pytest.raises(ValueError, match="inactive"):
        run.enter_branch("d", setup.refs[2])


def test_wrong_process_rejected(setup, monkeypatch):
    run = setup.open()
    monkeypatch.setattr(admission.os, "getpid", lambda: run._pid + 1)
    assert not run.active_for("a")
    with pytest.raises(ValueError, match="wrong_process"):
        run.enter_branch("a", setup.refs[2])


def test_wrong_run_overlap_duplicate_and_copied_payload_rejected(setup):
    run = setup.open()
    with pytest.raises(ValueError, match="wrong_run"):
        run.enter_branch("a", {**setup.refs[2], "sha256": "different"})
    with pytest.raises(ValueError, match="missing_branch"):
        run.enter_branch("undeclared", setup.refs[2])
    run.enter_branch("a", setup.refs[2])
    with pytest.raises(ValueError, match="overlapping"):
        run.enter_branch("b", setup.refs[2])
    altered = run.contract_copy("a")
    altered["contract"]["binary_sha256"] = "forged"
    assert run.contract_copy("a")["contract"]["binary_sha256"] == "binary"
    run.finish_branch("a")
    with pytest.raises(ValueError, match="duplicate"):
        run.enter_branch("a", setup.refs[2])
    run.close()


def test_active_run_cannot_authorize_changed_case_or_method(setup):
    run = setup.open(); run.enter_branch("a", setup.refs[2])
    with pytest.raises(ValueError, match="branch_action_domain_changed"):
        runner.run_branch(None, {"case": "a", "method": "foreign", "fault": None}, setup.refs[0], {},
                          accepted_run=run, branch_key="a")
    run.finish_branch("a"); run.close()


@pytest.mark.parametrize("name", ["source", "raw"])
@pytest.mark.parametrize("phase", ["before_branch", "during_branch", "before_close"])
def test_each_file_change_invalidates_whole_run(setup, name, phase):
    run = setup.open()
    if phase == "during_branch":
        run.enter_branch("a", setup.refs[2])
    getattr(setup, name).write_text("changed bytes\n")
    if phase != "before_close":
        with pytest.raises(ValueError, match="evidence_changed"):
            run.enter_branch("a", setup.refs[2]) if phase == "before_branch" else run.finish_branch("a")
    final = run.close()
    assert final["status"] == "invalidated_acceptance_evidence"
    assert not run.active_for("a")


def test_removed_file_fails_closed(setup):
    run = setup.open()
    setup.raw.unlink()
    with pytest.raises(ValueError, match="evidence_changed"):
        run.enter_branch("a", setup.refs[2])
    assert run.close()["status"] == "invalidated_acceptance_evidence"


def test_entry_change_during_verification_cannot_mint_capability(setup, monkeypatch):
    def verify(*args, **kwargs):
        setup.raw.write_text("mutation during closed gate")
        return copy.deepcopy(setup.verified)
    monkeypatch.setattr(admission.timing, "verify_contract", verify)
    with pytest.raises(ValueError, match="entry_bytes_changed"):
        setup.open()


def test_entry_rejects_boolean_or_missing_semantic_gate(setup):
    setup.verified["runtime_accepted"] = False
    with pytest.raises(ValueError, match="closed_runtime_gate_missing"):
        setup.open()
    setup.verified["runtime_accepted"] = True
    setup.semantic["passed"] = 20
    with pytest.raises(ValueError, match="closed_runtime_gate_missing"):
        setup.open()


def test_exit_exception_revokes_even_active_branch(setup, monkeypatch):
    run = setup.open(); run.enter_branch("a", setup.refs[2])
    monkeypatch.setattr(admission.semantic, "verify_saved_semantic_gate", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad_xml")))
    final = run.close()
    assert final["status"] == "invalidated_acceptance_evidence" and "bad_xml" in final["invalid"]
    assert not run.active_for("a")


def test_end_inventory_addition_invalidates(setup, monkeypatch):
    run = setup.open()
    monkeypatch.setattr(admission, "inventory", lambda *a: {**setup.pins, "new_source": "new"})
    assert run.close()["status"] == "invalidated_acceptance_evidence"


def test_session_collector_requires_active_exact_branch(setup, monkeypatch):
    Path(setup.refs[0]["path"]).write_text("contract")
    setup.refs[0]["sha256"] = admission.sha(setup.refs[0]["path"])
    run = setup.open(); run.enter_branch("a", setup.refs[2])
    native = SimpleNamespace(_g31_native_artifact_identity={"resolved_path": str(setup.source), "sha256": "binary"})
    session = SimpleNamespace(protocol_planning_snapshots_v3=lambda owner: [])
    monkeypatch.setattr(adapter.previous, "_trusted_native", lambda n, s: n is native and s is session)
    info, handle = adapter.bind_native027(native, session, setup.refs[0], accepted_run=run, branch_key="a")
    assert handle is not None and info["status"] == "accepted_native027_session"
    # The genuine runtime collector also checks contract bytes each use.
    assert adapter._valid_handle(native, session, handle)
    assert not adapter._valid_handle(native, SimpleNamespace(), handle)
    run.finish_branch("a")
    assert not adapter._valid_handle(native, session, handle)
    info, forged = adapter.bind_native027(native, session, setup.refs[0], accepted_run=run.audit_copy(), branch_key="a")
    assert forged is None and info["status"] == "unknown"
    assert run.close()["status"] == "closed_run_acceptance_passed"


def definition(module, name):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return ast.dump(next(row for row in tree.body if isinstance(row, (ast.FunctionDef, ast.ClassDef)) and row.name == name), include_attributes=False)


@pytest.mark.parametrize("name", ["OwnerPolicy", "owner_first_action", "assess_cell", "assess", "native_scene"])
def test_policy_physics_assessment_ast_unchanged(name):
    assert definition(runner, name) == definition(original, name)


def test_same_declared_nine_and_sixty_rows_without_native():
    for phase in ("delivery_gate", "business"):
        a, b = runner.protocol(phase), original.protocol(phase)
        assert a["rows"] == b["rows"]
        assert a["row_configuration_sha256"] == b["row_configuration_sha256"]
        assert a["native_branch_budget"] == b["native_branch_budget"] == (9 if phase == "delivery_gate" else 60)


def test_inventory_covers_every_closed_evidence_family(tmp_path, monkeypatch):
    monkeypatch.setattr(admission, "ROOT", tmp_path)
    made = set()
    def put(relative, value):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(value).encode() if not isinstance(value, bytes) else value)
        made.add(str(path.resolve()))
        return path
    def ref(path): return {"path": str(path), "sha256": admission.sha(path)}
    source = put("scripts/source.py", b"source bytes")
    compiled = put("build/source/compiled.hpp", b"compiled bytes")
    binary = put("build/native.pyd", b"native binary")
    interpreter = put("python.exe", b"interpreter")
    build = put("build/receipt.json", {"source_after": {"compiled.hpp": admission.sha(compiled)}})
    base = {"build_receipt": str(build), "source_archive": str(compiled.parent),
            "binary": str(binary), "binary_sha256": admission.sha(binary)}
    candidate = put("candidate.json", {**base, "runtime_acceptance": None})
    put("gate/candidate_contract.json", read_bytes := candidate.read_bytes())
    put("gate/contract_reference.json", ref(candidate))
    gate_input = put("gate/inputs/example.json.gz", b"compressed gate input")
    gate_source = put("gate/source/scripts/source.py", source.read_bytes())
    process = put("gate/plain.process.json", {"exit_code": 0})
    completed = put("gate/plain/completion.json", {"status": "complete"})
    raw = put("gate/plain/example.json.gz", b"compressed raw")
    gate_plan = put("gate/plan.json", {"contract_reference": ref(candidate), "native026_build": str(build),
        "native026_source_archive": str(compiled.parent), "native026_binary": str(binary),
        "native026_sha256": admission.sha(binary), "source_sha256": {str(source): admission.sha(source)},
        "input_sha256": {"example": admission.sha(gate_input)}})
    gate_receipt = put("gate/receipt.json", {"plan_sha256": admission.sha(gate_plan),
        "raw": {"plain": {"example": admission.sha(raw)}}, "process_sha256": {"plain": admission.sha(process)},
        "completion_sha256": {"plain": admission.sha(completed)}})
    contract = put("accepted.json", {**base, "runtime_acceptance": ref(gate_receipt)})
    semantic_plan = put("semantic/plan.json", {"interpreter": str(interpreter), "interpreter_sha256": admission.sha(interpreter),
        "build_receipt": str(build), "binary": str(binary), "binary_sha256": admission.sha(binary),
        "source_sha256": {str(source): admission.sha(source)}})
    semantic_source = put("semantic/source/scripts/source.py", source.read_bytes())
    semantic_process = put("semantic/process.json", {"exit_code": 0})
    semantic_worker = put("semantic/worker.json", {"loaded": "exact"})
    xml = put("semantic/tests.xml", b"<testsuite tests='21'/>")
    semantic_receipt = put("semantic/receipt.json", {"evidence_sha256": {p.name: admission.sha(p)
        for p in (semantic_plan, semantic_process, semantic_worker, xml)}})
    campaign_source = put("campaign/source/scripts/source.py", source.read_bytes())
    campaign_input = put("campaign/inputs/case/method.json", {"input": "same"})
    campaign = put("campaign/preregistered_protocol.json", {"source_sha256": {str(source): admission.sha(source)},
        "source_archive": {str(source): "source/scripts/source.py"},
        "input_file_sha256": {"case/method": admission.sha(campaign_input)}})
    pins = admission.inventory(ref(contract), ref(semantic_receipt), ref(campaign))
    assert set(pins) == made | {str(Path(admission.__file__).resolve())}
    assert all(admission.sha(path) == digest for path, digest in pins.items())
    for path in (source, compiled, binary, interpreter, candidate, gate_input, gate_source, process,
                 completed, raw, semantic_source, semantic_worker, xml, campaign_source, campaign_input):
        old = path.read_bytes(); path.write_bytes(old + b"mutation")
        assert admission.sha(path) != pins[str(path)]
        path.write_bytes(old)


def test_worker_exception_always_finalizes_admission(setup, monkeypatch, tmp_path):
    run = setup.open()
    monkeypatch.setattr(runner, "imported_sources", lambda: [])
    monkeypatch.setattr(runner, "sha", lambda path: "same")
    monkeypatch.setattr(runner.run_admission, "open_run", lambda *a: run)
    monkeypatch.setattr(runner, "_admitted_worker", lambda *a: (_ for _ in ()).throw(ValueError("simulated setup exception")))
    (tmp_path / "preregistered_protocol.json").write_text(json.dumps({"source_sha256": {}}))
    args = SimpleNamespace(output=tmp_path, binary=tmp_path / "binary", expected_binary_sha256="same",
        native_contract=tmp_path / "contract", expected_native_contract_sha256="contract",
        semantic_gate=tmp_path / "semantic", expected_semantic_gate_sha256="semantic")
    with pytest.raises(ValueError, match="simulated setup"):
        runner.worker(args)
    assert run._closed and not run._active
    assert json.loads((tmp_path / "run_acceptance.json").read_text())["status"] == "closed_run_acceptance_passed"
