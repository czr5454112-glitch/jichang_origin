"""SYNTHETIC phase-control QA; no process or real pool is launched."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import uuid
from unittest.mock import patch

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_campaign_v3 as master
from scripts.eval import run_feng_paper_suite_campaign_v2 as old_master
pool = master.pool
OUT = ROOT / "build/paper_suite_reduced_campaign_v3_qa" / uuid.uuid4().hex[:12]
OUT.mkdir(parents=True)
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)


def reject(name, action):
    try:
        action()
    except (ValueError, FileNotFoundError):
        checks.append(name)
    else:
        raise AssertionError(name)


old = pool.read(old_master.PLAN)
reduced = copy.deepcopy(old)
reduced["cells"] = [c for c in reduced["cells"] if pool.family(c["family"]) == "base" or
                     (c["scenario_index"] in master.FAULT_SCENARIOS and c["seed"] in master.FAULT_SEEDS)]
reduced.update(cell_count=576, family_counts={"base":480, "all_day_fault":96}, execution_order=["base", "all_day_fault"])
synthetic_plan = OUT / "synthetic_reduced_plan.json"
pool.write(synthetic_plan, reduced)
plan = pool.load_plan(synthetic_plan)
base, fault = master.stage_cells(plan)
all_base = pool.select_cells(plan, {"family":["base"]})
all_fault = pool.select_cells(plan, {"family":["all_day_fault"]})
check("selected_dimensions_16_480_8_96_total576", [len(base), len(all_base), len(fault), len(all_fault),len(plan["cells"])] == [16,480,8,96,576])
check("all_480_base_cells_byte_identical_in_plan", all_base == [c for c in old["cells"] if c["family"] == "base"])
check("fault_only_four_scenarios_three_shared_seeds", {c["scenario_index"] for c in all_fault} == {1,2,9,14}
      and {c["seed"] for c in all_fault} == {104729,130363,155921})
check("all_selected_faults_retain_original_input_output_and_runner", all(c in old["cells"] for c in all_fault))
for name, mutate in (
    ("unselected_scenario", lambda p: next(c for c in p["cells"] if c["scenario_index"] == 9).update(scenario_index=3)),
    ("unselected_seed", lambda p: next(c for c in p["cells"] if c["scenario_index"] == 9).update(seed=999999)),
    ("fault_first_order", lambda p:p.update(execution_order=["all_day_fault","base"])),
    ("missing_execution_order", lambda p:p.pop("execution_order")),
    ("wrong_family_count", lambda p:p.update(family_counts={"base":480,"all_day_fault":1280})),
    ("missing_base_cell", lambda p:p["cells"].remove(next(c for c in p["cells"] if c["family"]=="base"))),
):
    bad = copy.deepcopy(plan)
    mutate(bad)
    reject(name + "_rejected", lambda:master.stage_cells(bad))
reject("old_1760_plan_not_reinterpreted_as_reduced", lambda:master.stage_cells(old))


def run_mock(fail_stage=None, fail_normal2=False, held_lock=False):
    campaign = master.Campaign.__new__(master.Campaign)
    campaign.root = OUT / ("phase_" + uuid.uuid4().hex[:8])
    campaign.token, campaign.run_id = uuid.uuid4().hex, "synthetic_qa"
    campaign.directory, campaign.lock = campaign.root / "master", campaign.root / "master.lock"
    campaign.plan, campaign.base, campaign.fault = plan, base, fault
    campaign.all_base, campaign.all_fault = all_base, all_fault
    campaign.status = {"status":"STARTING", "phase":"SYNTHETIC_QA", "phases":[], "prerequisites":[]}
    calls = []
    campaign.unchanged = lambda:None
    campaign.report = lambda:calls.append("report")
    if held_lock:
        campaign.root.mkdir()
        (campaign.root / ".paper_suite_orchestration.lock").write_text("SYNTHETIC OTHER OWNER",encoding="utf-8")
    def wait_for(name, probe):
        calls.append(name)
        if name == "phase2_wait_normal_full_2x" and fail_normal2:
            raise ValueError("SYNTHETIC failed normal2 gate")
        return {"status":"PASS", "name":name}
    campaign.wait_for = wait_for
    def fake_pool(plan_arg, cells, **kwargs):
        calls.append((len(cells), kwargs))
        failure = len(cells) == fail_stage
        return {"status":"FAILED" if failure else "COMPLETE", "accepted_count":len(cells)-int(failure)}
    with patch.object(master,"prerequisites",return_value=[{"name":"synthetic"}]), \
         patch.object(pool,"run_plan",side_effect=fake_pool), \
         patch.object(pool.subprocess,"Popen",side_effect=AssertionError("native launch forbidden")):
        result = campaign.run()
    return result,calls,campaign


expected_order = ["wait_for_reporter", "wait_for_existing_hca_dh_pool", 16,
                  "phase2_wait_normal_full_2x",480,8,96,"report"]
result,calls,_ = run_mock()
check("base480_finishes_before_any_fault_dispatch", [x[0] if isinstance(x,tuple) else x for x in calls] == expected_order
      and result["status"] == "COMPLETE")
check("four_worker_resume_failure_contract_retained", all(x[1] == {"workers":4,"timeout_seconds":0,"keep_going":False}
      for x in calls if isinstance(x,tuple)))
for stage,expected in ((16,[16]),(480,[16,480]),(8,[16,480,8]),(96,[16,480,8,96])):
    result,calls,_ = run_mock(fail_stage=stage)
    check(f"failure_at_{stage}_prevents_later_dispatch", result["status"] == "FAILED"
          and [x[0] for x in calls if isinstance(x,tuple)] == expected and calls[-1] == "report")
result,calls,_ = run_mock(fail_normal2=True)
check("normal2_failure_blocks_base480_and_all_faults", result["status"] == "FAILED"
      and [x[0] for x in calls if isinstance(x,tuple)] == [16])
result,calls,campaign = run_mock(held_lock=True)
check("another_pool_lock_prevents_dispatch_and_is_preserved", result["status"] == "FAILED"
      and not any(isinstance(x,tuple) for x in calls)
      and (campaign.root / ".paper_suite_orchestration.lock").read_text() == "SYNTHETIC OTHER OWNER")
check("initial_pool_and_normal_controls_unchanged", all(getattr(master,key) == getattr(old_master,key)
      for key in ("EXISTING_POOL","NORMAL1","NORMAL2","MICRO14","CPP4","TARAU8","FAULT4","BINARY_SHA")))
check("uses_fixed_new_reporter", master.REPORTER == ROOT / "scripts/eval/report_feng_paper_suite_v2.py")
protected = {
    "scripts/eval/run_feng_paper_suite_campaign_v2.py":"f54cb192544c7213d2665b108ba044dbb2e350db3923605fcfde1c104b87d4f4",
    "scripts/eval/run_feng_paper_suite_v2.py":"a5fc0798e13b8a3ab6c13bd9f96627c05aa8058a2aa15181d8cf8a1b2bfea827",
}
check("old_running_master_and_pool_bytes_unchanged", all(pool.sha(ROOT/name)==value for name,value in protected.items()))
final = pool.load_plan(master.PLAN)
check("actual_frozen_V6_identity", final["_sha256"] == master.PLAN_SHA and len(final["cells"]) == 576)
check("actual_frozen_V6_matches_exact_reduced_cells", final["cells"] == plan["cells"])
actual_base,actual_fault = master.stage_cells(final)
check("actual_frozen_V6_registered_stages", len(actual_base)==16 and len(actual_fault)==8
      and final["execution_order"]==["base","all_day_fault"])
references = master.verify_scope(final)
check("actual_scope_contract_and_parent_V5_chain", len(references)==2
      and references[1]["sha256"] == "00a95b47298fb1aac808bec9275f6d9b3c28d340859017c0667e39ff736b9719")
for name, mutate in (
    ("scope_SHA", lambda p:p["scope_contract"].update(sha256="0"*64)),
    ("parent_SHA", lambda p:p["scope_reduction"].update(source_plan_sha256="0"*64)),
    ("retained_cell_entry", lambda p:p["cells"][0].update(runner_sha256="0"*64)),
    ("removed_population", lambda p:p["scope_reduction"].update(removed_count=1183)),
    ("user_approval", lambda p:p["scope_reduction"].update(user_approved=False)),
):
    bad = copy.deepcopy(final)
    mutate(bad)
    reject(name + "_tamper_rejected", lambda:master.verify_scope(bad))
result = dict(status="PASS", label="SYNTHETIC QA plus actual plan read-only validation", check_count=len(checks),
              checks=checks, native_simulations_invoked=0, real_pools_started=0, process_control_invoked=0,
              protected_sources=protected, source_sha256=pool.sha(Path(master.__file__)),
              plan_sha256=final["_sha256"], plan_path=str(master.PLAN), fixture_directory=str(OUT),
              limitation="Pool dispatch is mocked; this does not establish 576 completed experiments.")
pool.write(OUT/"verification.json",result)
print(json.dumps(dict(status="PASS",check_count=len(checks),output=str(OUT/"verification.json"))))
