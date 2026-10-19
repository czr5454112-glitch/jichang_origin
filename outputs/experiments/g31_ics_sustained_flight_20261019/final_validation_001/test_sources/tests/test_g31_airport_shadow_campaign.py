"""Pure orchestration: no native construction, forecast or model forward."""
import copy
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_shadow_campaign as campaign


@pytest.mark.parametrize('arguments,stdin',[
    ([],''),(['--admission','token'],''),(['--admission','token'],'wrong\n'),(['--admission'],''),
])
def test_worker_admission_precedes_any_delegate_import(tmp_path,arguments,stdin):
    path=tmp_path/'absent'
    result=subprocess.run([sys.executable,'-X','importtime','-m',campaign.MODULE,
        '--worker','--output',str(path),*arguments],input=stdin,text=True,capture_output=True,
        timeout=15,cwd=campaign.ROOT)
    assert result.returncode!=0 and 'airport_shadow:missing_parent_job_admission' in result.stderr
    assert 'foundation_airport_recorded_campaign' not in result.stderr
    assert 'foundation_airport_recorded_budget_campaign' not in result.stderr
    assert not path.exists()


def test_valid_token_can_show_help_without_configuration_or_native():
    result=subprocess.run([sys.executable,'-m',campaign.MODULE,'--worker','--admission','token','--help'],
        input='token\n',text=True,capture_output=True,timeout=15,cwd=campaign.ROOT)
    assert result.returncode==0 and '--model-manifest' in result.stdout


def test_outer_callback_timer_includes_recorder_and_returns_same_object():
    value={'intents':[{'source':1}]};ticks=[0.]
    shadow=SimpleNamespace(results=[])
    class Recorder:
        def wrap(self,_):
            def callback(obs,**options):
                ticks[0]+=2 # capture
                shadow.results.append({'inner_elapsed':3})
                ticks[0]+=3 # baseline and shadow
                ticks[0]+=5 # references/blob/event storage
                return value
            return callback
    callback=campaign.timed_recorded_callback(Recorder(),shadow,clock=lambda:ticks[0])
    assert callback({'now':57840}) is value
    assert shadow.results[0]['entire_recorded_callback_elapsed_including_all_storage_seconds']==10


def test_runtime_target_projection_excludes_all_future_evidence_and_reference_commands():
    identity={'owner_id':'A','now':57840.,'sequence':1,'residual_index':0,'request_prefix':'protocol:1'}
    source={'selected':[{'callback':{**identity,'segment_raw':{'path':'private_outcome'}},
                        'actual_request':{'future_id':7},'first_edge_delay_seconds':5.,'positive_acks':[1]}]}
    assert campaign.runtime_targets(source)==[{'callback':identity}]


def test_configuration_changes_only_hooks_and_metadata_in_memory(monkeypatch):
    base=campaign.delegate;budget=campaign.budget
    unchanged={name:getattr(base,name) for name in ['worker','launch','apply_policy','registered_planner','execute_bounded_continuous']}
    for name in ['MODULE','SCHEMA','SOFT_SECONDS','HARD_SECONDS','SOURCE_ROOTS','soft_checkpoint_contract','check_pins','execute_continuous']:
        monkeypatch.setattr(base,name,getattr(base,name))
    monkeypatch.setattr(budget,'_configured',False);monkeypatch.setattr(campaign,'_configured',False)
    assert campaign.configure() is base
    assert all(getattr(base,name) is value for name,value in unchanged.items())
    assert base.check_pins is campaign.check_pins and base.execute_continuous is campaign.execute_continuous
    assert (base.SOFT_SECONDS,base.HARD_SECONDS)==(600,660)
    assert base.SOURCE_ROOTS[0]==campaign.MODULE
    assert campaign.contract()['scores_select_action'] is False


def test_preparation_requires_actual_artifacts_before_output_exists(tmp_path):
    result=subprocess.run([sys.executable,'-m',campaign.MODULE,'--prepare','--output',str(tmp_path/'none')],
        text=True,capture_output=True,timeout=15,cwd=campaign.ROOT)
    assert result.returncode!=0 and 'actual_model_manifest_required_no_placeholders' in result.stderr
    assert not (tmp_path/'none').exists()


def test_plan_comparison_rejects_changed_physics_even_when_base_gate_is_stubbed(monkeypatch):
    old={'schema':'old','branch':'C00','source_sha256':{},'controller':{'tick':60},
         'scope':'old','input':{'path':'old'},'output':'old'}
    plan={**copy.deepcopy(old),'schema':campaign.SCHEMA,'scope':campaign.contract()['purpose'],
          'controller':{'tick':30},'behavior_shadow':{'baseline_plan':{}},'mapping':{}}
    old['mapping']={}
    monkeypatch.setattr(campaign,'_BASE_CHECK',lambda _:None)
    monkeypatch.setattr(campaign,'validate_resources',lambda *_:({'selected':[]},None,None,None))
    monkeypatch.setattr(campaign,'read',lambda _: {})
    plan['behavior_shadow']['runtime_targets']='targets'
    monkeypatch.setattr(campaign,'bound',lambda ref:[] if ref=='targets' else old)
    plan['mapping']={'path':'x'};old['mapping']={'path':'x'}
    with pytest.raises(ValueError,match='shadow_same_baseline_field:controller'):campaign.check_pins(plan)
