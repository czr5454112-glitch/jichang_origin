"""Independent, stdlib-only saved prelaunch review. No producer imports or replay.

Run only after root review of this file. Reads bounded metadata/source files; never
opens gzip, API manifests, service clocks, or the large final raw tree. This is
not an actual600 entry/exit authority check and is not a whole-day certificate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(r"C:\PROGRAMING\czr005\.g31_ics_circulation_worktree")
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
TARGET = OUT / "bcdm1"
PYTHON = Path(r"C:\PROGRAMING\python3.11.9\python.exe")
PYTHON_SHA = "5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec"
MODULE = "scripts.experiments.g31_ics_circulation.audit_bridge_saved_c_digest_v2"
ENV = {"PYTHONPATH": "src;.;tests", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONIOENCODING": "utf-8"}
PLAN_SHA = "ce7168ac603be884b45c8822aefadef70a65a0f546971a4b675e52539af87b57"
PREP_SHA = "7d8244159213584e73415188f1ae383dd9c42b96c7c586ca81deab63b018c7d8"
META_SHA = "6b98b3ec7cec324b4c3e896c15086964c6d685007efd25fd97223ba8885727ed"
ACTUAL_WRAPPER = OUT / "control_timers_bcdm1_saved600_001.ps1"
ACTUAL_WRAPPER_SHA = "97afe655ed1f124fc51ff3840d8ad5769f6d7e973b0c5c0258661fa0d56d809b"
META_WRAPPER_SHA = "f6c972365c5c5cf14baab222361c853a8c316145821e43f28cd9da75b52b789f"
HIST = OUT / "bridge_saved_text_actor_prepare_001"
HIST_PINS = {
    "plan.json": "6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a",
    "bounded_execution.json": "76d3bdce5b7775a7cbfa53658a98f3cbbfe3b8ffbd32dbe65e248c35e3510b56",
    "external_application_wall.json": "8215f25b11efe738bece294b5c9fc98d05a66d28095f5ba2eed44770979940b1",
    "progress.jsonl": "7c4da24ecc7dff5365243d557997410f819bb4cfa2b891e4faa6dd521a5489ac",
}
GATES = {
    "bcdp2": {
        "tests": 27, "sources": 138, "module": "run_bridge_saved_c_digest_driver_pure_v2",
        "schema": "g31.bridge.saved_C_digest.driver_pure.v2",
        "external_schema": "g31.bridge.saved_C_digest.driver_pure_external.v1",
        "wrapper_sha": "1943b29c396375d216d7885fb68080136b836a66df9b56938f3cba1e0c9f480e",
        "plan": "3cec8d06031be2dc7b41af3f5fca6c9e7e3ec43399ef0bda071e7d8ac0ee4c22",
        "receipt": "f4f880adc9d659a2f0cc9f96ab40fac6b85b554ac837fe86fd6c4cd1918ef285",
        "external": "143ace300e68d8f9e6a8f4fe2a0b5f6dd438229a6d1ea4668508af5cdf9f66bd",
        "review": "b61f2bf610fc67d349c418fda042967daa6f137979af51b11b710d29b5bbed46",
    },
    "bcp2": {
        "tests": 37, "sources": 115, "module": "run_bridge_saved_c_digest_pure_v2",
        "schema": "g31.bridge.saved_C_digest.synthetic_pure.v2",
        "external_schema": "g31.bridge.saved_C_digest.pure_external.v1",
        "wrapper_sha": "9150c283af1df06c502b81a79e98d05ab1336923110d1482a54f6738f9816ff7",
        "plan": "9fd532c6051eefa0c1446fbe958a413e320a73f6dfec98e0ddd5e4a63987b780",
        "receipt": "174838c6c05a7893f5b8f600ba623c84e72c49126b315c9a9384c7e19f1b9392",
        "external": "af80bdd5c93b9db0507bf8c043ba17e7c6f7803ea5b029a9d51f58738a3f1918",
        "review": "4db25792478f03dac007cc6466148c4ddc55fce98407ee2f551bb2c974b7df7c",
    },
}
ADDED = {
    "scripts/experiments/g31_ics_circulation/bridge_audit_source_union.py": "28418dc6e928e1a9f4987e15bcf610e4400c2e9d8fdf0aedff55169b71998efa",
    "scripts/experiments/g31_ics_circulation/audit_bridge_saved_c_digest_v2.py": "1accbd24e4b0408c9c5cad63eaf06095eefb77d9d751d94e9161f577541055d3",
    "scripts/experiments/g31_ics_circulation/run_bridge_saved_c_digest_driver_pure_v2.py": "1523e43f9d0f00db4238a671057c1104586d21b017f3bb49088ca4d8bf5a8ee7",
    "tests/test_g31_circulation_bridge_audit_source_union.py": "2143808845257cc3bd4fa5e9b918a2d4e8800e9a66f054d6488a564daeb8872a",
}
SEEN: dict[str, str] = {}
READ_BYTES = 0
MAX_FILE = 16 * 1024 * 1024


def require(condition, label):
    if not condition:
        raise ValueError(label)


def exact(a, b, label):
    # Ordered JSON distinguishes bool/int/float and signed zero. All inputs here
    # are strict-decoded metadata, not arbitrary Python objects or user hooks.
    encode = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    require(encode(a) == encode(b), label)


def integer(v, label, minimum=0):
    require(type(v) is int and v >= minimum, label)
    return v


def finite(v, label):
    require(type(v) in (int, float) and math.isfinite(v) and v >= 0, label)
    return v


def canonical(path, parent=ROOT):
    p = Path(path)
    require(p.is_absolute() and str(p) == str(p.resolve()), "noncanonical:" + str(p))
    require(p != parent and p.is_relative_to(parent) and len(str(p)) < 260, "path_domain:" + str(p))
    return p


def relative_path(name, parent=ROOT):
    require(type(name) is str and "\\" not in name and not Path(name).is_absolute(), "relative_source")
    require(name and all(x not in ("", ".", "..") for x in name.split("/")), "relative_components")
    p = canonical(parent / name, parent)
    require(p.relative_to(parent).as_posix() == name, "relative_roundtrip")
    return p


def read(path, expected=None):
    global READ_BYTES
    p = Path(path)
    if p != PYTHON:
        canonical(p)
    require(p.suffix.lower() != ".gz" and p.name not in ("manifest.jsonl", "service_clocks.jsonl"), "large_evidence_forbidden")
    require(p.is_file() and p.stat().st_size <= MAX_FILE, "bounded_small_file:" + str(p))
    with p.open("rb") as stream:
        data = stream.read(MAX_FILE + 1)
    require(len(data) <= MAX_FILE, "file_grew")
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None:
        require(type(expected) is str and re.fullmatch("[0-9a-f]{64}", expected) and digest == expected, "hash:" + str(p))
    if str(p) in SEEN:
        require(SEEN[str(p)] == digest, "within_review_drift:" + str(p))
    SEEN[str(p)] = digest
    READ_BYTES += len(data)
    return data


def pairs(rows):
    out = {}
    for key, value in rows:
        require(key not in out, "duplicate_json_key")
        out[key] = value
    return out


def reject_constant(value):
    raise ValueError("nonfinite_json:" + value)


def load(path, expected=None):
    return json.loads(read(path, expected).decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=reject_constant)


def source_archive(pins, directory, count):
    require(type(pins) is dict and len(pins) == count, "source_count")
    identities = set()
    archive = canonical(directory / "source")
    for name, digest in pins.items():
        live = relative_path(name)
        saved = relative_path(name, archive)
        identity = str(live).casefold()
        require(identity not in identities and saved != live, "source_alias")
        identities.add(identity)
        read(live, digest)
        read(saved, digest)


def external_clock(v, command, wrapper, wrapper_sha, schema):
    exact(v["schema"], schema, "external_schema")
    exact(v["command"], command, "external_command")
    exact(v["working_directory"], str(ROOT), "external_cwd")
    exact(v["environment_explicit"], ENV, "external_environment")
    exact(v["python"], {"path": str(PYTHON), "sha256": PYTHON_SHA}, "external_python")
    exact(v["wrapper"], {"path": str(wrapper), "sha256": wrapper_sha}, "external_wrapper")
    read(wrapper, wrapper_sha)
    for key, expected in {"started": True, "exit_code": 0, "outer_timeout": False,
                          "exception": None, "cleanup_errors": [], "source_changed": [], "missing_outputs": []}.items():
        exact(v[key], expected, "external_" + key)
    start = integer(v["start_ticks"], "start_ticks")
    end = integer(v["end_ticks"], "end_ticks")
    elapsed = integer(v["elapsed_ticks"], "elapsed_ticks")
    frequency = integer(v["tick_frequency"], "tick_frequency", 1)
    require(end >= start and elapsed == end - start, "tick_conservation")
    require(integer(v["budget_ticks"], "budget_ticks") == 120 * frequency and elapsed <= 120 * frequency, "typed120")
    require(abs(finite(v["whole_python_seconds"], "whole_wall") - elapsed / frequency) <= 1e-9, "clock_formula")


def gate(name):
    spec = GATES[name]
    directory = OUT / name
    plan = load(directory / "plan.json", spec["plan"])
    receipt = load(directory / "receipt.json", spec["receipt"])
    ext = load(directory / "external_application_wall.json", spec["external"])
    review = load(directory / "root_saved_review_001.json", spec["review"])
    command = [str(PYTHON), "-m", "scripts.experiments.g31_ics_circulation." + spec["module"], "--output", str(directory)]
    external_clock(ext, command, OUT / ("control_timers_" + name + "_pure_001.ps1"), spec["wrapper_sha"], spec["external_schema"])
    exact(ext["accepted_launch_and_clock"], True, "pure_external_acceptance")
    exact(ext["expected_tests"], spec["tests"], "pure_expected")
    required = {"plan.json", "receipt.json", "worker.json", "bounded_execution.json", "tests.xml", "parent_stdout.log", "parent_stderr.log"}
    if name == "bcdp2":
        required |= {"parent_stages.jsonl", "worker_stages.jsonl"}
    require(set(ext["output_sha256"]) == required, "pure_output_domain")
    for leaf, digest in ext["output_sha256"].items():
        read(relative_path(leaf, directory), digest)
    exact(ext["output_sha256"]["plan.json"], spec["plan"], "plan_output_pin")
    exact(ext["output_sha256"]["receipt.json"], spec["receipt"], "receipt_output_pin")
    for obj in (plan, receipt):
        exact(obj["schema"], spec["schema"], "pure_schema")
        exact(obj["tests"], spec["tests"], "pure_tests")
    exact(plan["limit_seconds"], 120.0, "pure_limit")
    require(type(plan["admission"]) is str and re.fullmatch("[0-9a-f]{32}", plan["admission"]), "pure_admission")
    exact(plan["command"], command + ["--worker", "--admission", plan["admission"]], "owned_worker_command")
    exact(receipt["status"], "passed_synthetic_routing", "pure_status")
    exact(receipt["expected_tests"], spec["tests"], "receipt_tests")
    exact(receipt["bad_tests"], [], "bad_tests")
    exact(receipt["error"], None, "pure_error")
    process = load(directory / "bounded_execution.json", ext["output_sha256"]["bounded_execution.json"])
    exact(receipt["process"], process, "owned_receipt")
    for key, val in {"status": "exited", "exitcode": 0, "windows_job_kill_on_close": True, "child_released_only_after_job_assignment": True}.items():
        exact(process[key], val, "owned_" + key)
    require(0 < finite(process["hard_timeout_seconds"], "owned_limit") <= 120 and finite(process["wall_seconds"], "owned_wall") <= 120, "owned120")
    worker = load(directory / "worker.json", receipt["worker_sha256"])
    exact(receipt["worker_sha256"], ext["output_sha256"]["worker.json"], "worker_pin")
    exact(worker["pytest_exitcode"], 0, "pytest_exit")
    exact(worker["source_entry_exit_exact"], True, "worker_sources_exact")
    for obj in (receipt, worker):
        for key in ("native_calls", "extension_loads", "actual_fixture_reads"):
            exact(obj[key], 0, "pure_zero_" + key)
    exact(receipt["benchmark_executed"], False, "pure_benchmark")
    exact(receipt["source_sha256"], plan["source_sha256"], "pure_source_map")
    source_archive(plan["source_sha256"], directory, spec["sources"])
    for domain in (receipt["loaded_parent_exit"], worker["loaded_entry"], worker["loaded_exit"]):
        require(type(domain) is list and len(set(domain)) == len(domain) and set(domain) <= set(plan["source_sha256"]), "loaded_source_domain")
    require(len(ext["source_sha256"]) == (4 if name == "bcdp2" else 5) and all(plan["source_sha256"].get(k) == v for k, v in ext["source_sha256"].items()), "external_source_subset")
    xml = ET.fromstring(read(directory / "tests.xml", receipt["XML_sha256"]))
    exact(receipt["XML_sha256"], ext["output_sha256"]["tests.xml"], "XML_pin")
    suites = list(xml.iter("testsuite"))
    cases = list(xml.iter("testcase"))
    require(len(cases) == spec["tests"] and sum(int(s.attrib["tests"]) for s in suites) == spec["tests"], "XML_denominator")
    require(all(int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped")), "XML_bad_counts")
    require(not any(list(xml.iter(tag)) for tag in ("error", "failure", "skipped")), "XML_bad_children")
    exact(review["status"], "passed_saved_only_readback", "root_gate_review")
    exact(review["tests"], spec["tests"], "root_gate_tests")
    exact(review["sources" if name == "bcdp2" else "source_count"], spec["sources"], "root_gate_sources")
    for leaf, digest in review["pins"].items():
        expected = spec["external"] if leaf == "external_application_wall.json" else ext["output_sha256"].get(leaf)
        require(expected is not None and expected == digest, "root_review_pin")
    return plan, receipt, ext, review


def main():
    began = time.perf_counter_ns()
    destination = TARGET / "root_execution_review_001.json"
    require(not destination.exists(), "preserve_existing_review")
    for leaf in ("actual_external_application_wall.json", "execution_claim.json", "bounded_execution.json", "report.json", "progress.jsonl", "stdout.log", "stderr.log", "C_encoder_entry.json", "C_encoder_exit.json", "all_job_states.json.gz", "failure.json"):
        require(not (TARGET / leaf).exists(), "preserve_actual_attempt:" + leaf)
    read(Path(__file__).resolve())
    read(PYTHON, PYTHON_SHA)
    require(Path(sys.executable).resolve() == PYTHON, "review_interpreter")
    read(ACTUAL_WRAPPER, ACTUAL_WRAPPER_SHA)
    plan = load(TARGET / "plan.json", PLAN_SHA)
    prep = load(TARGET / "preparation.json", PREP_SHA)
    meta = load(TARGET / "external_application_wall.json", META_SHA)
    metadata_command = [str(PYTHON), "-m", MODULE, "--prepare", "--output", str(TARGET), "--pure-receipt", str(OUT / "bcdp2/receipt.json")]
    actual_command = [str(PYTHON), "-m", MODULE, "--execute", "--output", str(TARGET), "--plan-sha256", PLAN_SHA]
    external_clock(meta, metadata_command, OUT / "control_timers_bcdm1_prepare_001.ps1", META_WRAPPER_SHA, "g31.bridge.saved_C_digest.metadata_external.v1")
    for key, value in {"metadata_checked": True, "metadata_error": None, "accepted_metadata_launch_and_clock": True, "source_count": 138}.items():
        exact(meta[key], value, "metadata_" + key)
    exact(meta["output_sha256"], {"plan.json": PLAN_SHA, "preparation.json": PREP_SHA}, "metadata_output_pins")
    for key, value in {"status": "prepared_source_review_pending", "plan_sha256": PLAN_SHA, "source_count": 138, "routing_pure_tests": 37, "driver_pure_executed": True, "driver_pure_tests": 27, "native_calls": 0, "predictions": 0, "extension_loads": 0, "saved_audit_executed": False, "large_evidence_reads_this_preparation": 0, "command": actual_command}.items():
        exact(prep[key], value, "preparation_" + key)
    driver, _, driver_ext, _ = gate("bcdp2")
    routing, _, routing_ext, _ = gate("bcp2")
    pins = driver["source_sha256"]
    exact(meta["source_sha256"], pins, "metadata_full_source_map")
    require(all(pins.get(k) == v for k, v in routing["source_sha256"].items()), "routing_subset")
    absolute = {str(relative_path(k)): v for k, v in pins.items()}
    exact(plan["source_before"], absolute, "absolute_plan_source_map")
    anchor = load(OUT / "bcdp1/plan.json", "df4bb1995188626493f7f9e93b709240c90472ad8c24a730b10219e543d44af4")
    old_domain = anchor["source_sha256"]
    require(len(old_domain) == 134 and not (set(old_domain) & set(ADDED)) and pins == old_domain | ADDED, "exact134_plus4")
    source_archive(old_domain, OUT / "bcdp1", 134)
    failed_prepare = load(OUT / "bcdp1/external_application_wall.json", "b81b5d0a409d4a49ad0c632eb3d084c645264973fdd75c05e77942706020a75f")
    exact(failed_prepare["outer_timeout"], True, "prior_pure_timeout_preserved")
    driver_refs = {k: {"path": str(OUT / "bcdp2" / k), "sha256": v} for k, v in driver_ext["output_sha256"].items()}
    driver_refs["external_application_wall.json"] = {"path": str(OUT / "bcdp2/external_application_wall.json"), "sha256": GATES["bcdp2"]["external"]}
    require(plan["driver_pure"] == driver_refs, "driver_pure_complete_refs")
    for leaf, digest in meta["pure_reference_sha256"].items():
        require(leaf in driver_refs and digest == driver_refs[leaf]["sha256"], "metadata_pure_pin")
    require(set(meta["pure_reference_sha256"]) == set(driver_refs) - {"parent_stdout.log", "parent_stderr.log"}, "metadata_pure_domain")
    scope = plan["preparation_scope"]
    exact(scope["large_evidence_reads"], 0, "no_preparation_large_reads")
    exact(scope["mandatory_full_recheck"], "At actual owned600 entry and exit.", "deferred_fullcheck")
    exact(scope["driver_gate_separate27_from_routing37"], True, "separate_gate_counts")
    expected_routing_refs = {str(OUT / "bcp2" / k): v for k, v in routing_ext["output_sha256"].items() if k not in ("parent_stdout.log", "parent_stderr.log")}
    expected_routing_refs[str(OUT / "bcp2/external_application_wall.json")] = GATES["bcp2"]["external"]
    expected_routing_refs[str(OUT / "bcp2/root_saved_review_001.json")] = GATES["bcp2"]["review"]
    require(scope["routing_pure_refs"] == expected_routing_refs, "routing_complete_refs")
    require(scope["large_hash_source"] == {str(HIST / k): v for k, v in HIST_PINS.items()}, "historical_metadata_refs")
    historical = load(HIST / "plan.json", HIST_PINS["plan.json"])
    previous_process = load(HIST / "bounded_execution.json", HIST_PINS["bounded_execution.json"])
    read(HIST / "external_application_wall.json", HIST_PINS["external_application_wall.json"])
    read(HIST / "progress.jsonl", HIST_PINS["progress.jsonl"])
    exact(previous_process["process"]["status"], "hard_timeout", "prior600_stays_timeout")
    allowed = {"schema", "source_before", "pure", "interpreter", "scope", "runtime_scope", "linear_contract", "preparation_scope", "driver_pure"}
    require(set(plan) == set(historical) | {"driver_pure"}, "plan_top_domain")
    for key in set(historical) - allowed:
        exact(plan[key], historical[key], "historical_equivalence:" + key)
    exact(plan["scope"], historical["scope"] + " New private C digest bundle only; no changes to physical policy or full saved checks.", "scope_only_C_change")
    exact(plan["schema"], "g31.bridge.saved_C_digest_audit.v2", "audit_schema")
    exact(plan["status"], "prepared_unexecuted", "unexecuted")
    exact(plan["hard_timeout_seconds"], 600.0, "fixed600")
    for key, value in {"expected_new_rows": 37270, "expected_old_prefix_rows": 27218, "native_calls": 0, "predictions": 0}.items():
        exact(plan[key], value, "full_denominator:" + key)
    contract = plan["linear_contract"]
    for key, value in {"fixed_seconds": 600, "new_rows": 37270, "old_complete_prefix_rows": 27218, "offered_jobs": 28506, "trays": 22}.items():
        exact(contract[key], value, "contract_denominator:" + key)
    exact(contract["historical_text_actor_contract"], historical["linear_contract"], "prior_actor_contract_exact")
    exact(plan["interpreter"], {"path": str(PYTHON), "sha256": PYTHON_SHA}, "plan_interpreter")
    exact(plan["pure"], {"path": str(OUT / "bcdp2/receipt.json"), "sha256": GATES["bcdp2"]["receipt"], "XML_path": str(OUT / "bcdp2/tests.xml"), "XML_sha256": driver_ext["output_sha256"]["tests.xml"]}, "plan_pure")
    producer = canonical(plan["source"])
    require(producer == OUT / "original_bridge_serialize_once_prepare_001", "fixed_original_producer")
    small_original = {"campaign.json", "external_application_wall.json", "external_launch_receipt.json", "branch_ledger.json", "root_prelaunch_review_001.json", "bridge/preregistered_protocol.json", "bridge/assessment.json", "bridge/worker_elapsed.json", "bridge/heartbeat.json", "bridge/worker.log", "bridge/verification.log"}
    for leaf in small_original:
        read(relative_path(leaf, producer), plan["original_refs"][leaf])
    producer_receipt = load(producer / "external_launch_receipt.json", plan["original_refs"]["external_launch_receipt.json"])
    exact(producer_receipt["status"], "unknown_shared_budget_overrun", "producer2400_not_upgraded")
    # C authority receipts/binary are bound metadata; no extension is imported.
    authority = contract["C_authority"]
    for path, digest in authority["files"].items():
        read(canonical(path), digest)
    binary = authority["binary"]
    for key in ("path", "archive"):
        require(len(read(canonical(binary[key]), binary["sha256"])) == binary["bytes"], "C_binary_size")
    c32 = contract["C32_root_review"]
    read(canonical(c32["path"]), c32["sha256"])
    snapshot = dict(SEEN)
    for path, digest in snapshot.items():
        read(Path(path), digest)
    result = {
        "schema": "g31.bcdm1.independent_execution_preflight.v1", "status": "ready_for_saved600",
        "helper": {"path": str(Path(__file__).resolve()), "sha256": SEEN[str(Path(__file__).resolve())]},
        "plan": {"path": str(TARGET / "plan.json"), "sha256": PLAN_SHA},
        "metadata_external_sha256": META_SHA, "preparation_sha256": PREP_SHA,
        "actual_wrapper": {"path": str(ACTUAL_WRAPPER), "sha256": ACTUAL_WRAPPER_SHA},
        "execute_command": actual_command, "metadata_whole_python_seconds": meta["whole_python_seconds"],
        "current_and_bcdp2_archive_sources": 138, "old134_archive_rechecked": True,
        "gates": {name: {"tests": spec["tests"], "root_review_sha256": spec["review"]} for name, spec in GATES.items()},
        "full_denominators": {"new_rows": 37270, "old_rows": 27218, "offered_jobs": 28506, "trays": 22, "separate_seconds": 600},
        "old_producer2400_and_saved600_still_failed": True,
        "deferred_original_refs": {k: v for k, v in plan["original_refs"].items() if k not in small_original},
        "deferred_checks": "All actual600 source/archive026/native binary, 7779 toolchain/3082 runtime dependencies, input/raw/manifests/every row, full policy/physical replay and output hashes remain mandatory at their original actual entry/exit sites. No old hash substitutes for those checks.",
        "progress_scope": "A completed row counter is only row validation/old-prefix comparison/actor construction; it does not prove that row's outer observer/policy consumption or the full certificate.",
        "checked_small_file_sha256": snapshot, "small_read_bytes_including_exit_rehash": READ_BYTES,
        "review_wall_before_export_seconds": (time.perf_counter_ns() - began) / 1e9,
        "native_calls": 0, "extension_loads": 0, "predictions": 0, "tests_rerun": 0, "large_raw_reads": 0,
        "scope": "Root-independent stdlib saved metadata/source review, using pinned historical plans and root gate reviews. No producer imports, source-graph recomputation, C load, native replay, whole-day validation or 100ms claim. Review export follows this clock; this is not a complete outside-process timing receipt.",
    }
    with destination.open("xb") as stream:
        stream.write((json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    print(json.dumps({"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "status": result["status"]}))


if __name__ == "__main__":
    main()
