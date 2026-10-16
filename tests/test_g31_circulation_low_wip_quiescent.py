"""Executable wrapper/verification pure gates; no current tape/native reads."""
import ast
from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import research_original_low_wip_quiescent as r
from scripts.experiments.g31_ics_circulation import verify_original_low_wip_quiescent as v
from scripts.experiments.g31_ics_circulation import review_original_low_wip_repeat_saved as review


def test_isolated_context_restores_every_reference_global_on_exception():
    before={key:getattr(r.reference,key) for key in r._original}
    with pytest.raises(RuntimeError):
        with r.installed():
            assert r.reference.RepeatOwner is r.candidate.RepeatOwner and r.reference.MODULE==r.MODULE
            assert r.reference.contract()['comparison_reference']['ready_sha256']==r.READY_SHA
            raise RuntimeError('forced')
    assert before=={key:getattr(r.reference,key) for key in before}


def test_source_closure_preserves_old72_and_absolute_runtime_and_new_verifier():
    actual=set(r.source_paths())
    assert set(r._original['source_paths']())<=actual
    for name in ('research_original_low_wip_quiescent.py','launch_original_low_wip_quiescent.py',
        'verify_original_low_wip_quiescent.py','repeat_quiescent_cap.py','review_original_low_wip_repeat_saved.py',
        'bounded_windows_job.py'):
        assert Path(r.__file__).with_name(name) in actual
    assert r.reference.ROOT/'scripts/eval/run_g4irsf28_service_potential.py' in actual


def test_campaign_rejects_prior_active_job_before_dispatch(monkeypatch,tmp_path):
    monkeypatch.setitem(r._original,'verify_campaign',lambda output:{})
    def forbidden(path):
        assert path==r.REFERENCE
        raise ValueError('prior_active')
    monkeypatch.setattr(review,'terminal_inventory',forbidden)
    with r.installed(require_terminal=True),pytest.raises(ValueError,match='prior_active'):
        r.verify_campaign(tmp_path)


def test_launcher_ast_changes_only_target_and_error_namespace():
    old=Path(r.__file__).with_name('launch_original_low_wip_repeat.py').read_text(encoding='utf8')
    new=Path(r.__file__).with_name('launch_original_low_wip_quiescent.py').read_text(encoding='utf8')
    old=old.replace('research_original_low_wip_repeat','research_original_low_wip_quiescent').replace('repeat_launch:','quiescent_launch:')
    a,b=ast.parse(old),ast.parse(new);a.body[0]=b.body[0]
    assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)


def write_tape(path,count,*,wall=1.):
    api=path/'api';api.mkdir(parents=True)
    manifest=[]
    for ordinal in range(count):
        name=f'{ordinal:06d}.json.gz'
        row={'ordinal':ordinal,'endpoint':'advance_to','args':[ordinal+1],'kwargs':{},'before':ordinal,'after':ordinal+1,
            'result':{'status':'reached','wall_seconds':wall}}
        with gzip.open(api/name,'wt',encoding='utf8') as f:json.dump(row,f)
        manifest.append({'path':name,'sha256':r.reference.base.sha(api/name)})
    (api/'manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in manifest),encoding='utf8')


def test_partial_old_manifest_keeps_valid_prefix_and_exposes_truncated_tail(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new';write_tape(old,1);write_tape(new,2,wall=2.)
    with (old/'api/manifest.jsonl').open('a') as f:f.write('{truncated')
    rows,tail=v.prefix_rows(old,partial=True)
    assert len(rows)==1 and tail['first_unverified_ordinal']==1
    report=v.compare_prefix(old,new,1,partial_left=True)
    assert report['verified_rows']==1 and report['left_unverified_tail']
    with pytest.raises(ValueError):v.prefix_rows(old)


def test_prefix_never_removes_physical_or_nan_clock_differences(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write_tape(a,1);write_tape(b,1,wall=float('nan'))
    with pytest.raises(ValueError):v.compare_prefix(a,b,1)


@pytest.mark.parametrize('key',['jobs','trays','receipts','physical_audit'])
def test_completed_old_arm_requires_exact_physical_results(key):
    old={'physical_time':86400.,'result':{'jobs':[],'trays':[],'receipts':[]},'physical_audit':{'status':'passed'}}
    new=deepcopy(old)
    if key=='physical_audit':new[key]={'status':'failed'}
    else:new['result'][key]=[{'different':True}]
    with pytest.raises(ValueError,match='physical_result_difference'):v.compare_physical(old,new)


def test_old_worker0_verifier1_is_only_candidate_for_corrected_review_not_promotion():
    assert v.completed_reference_case({'status':'unknown_incomplete_case','execution':{'exit_code':0},'verification':{'exit_code':1}})
    assert not v.completed_reference_case({'execution':{'exit_code':None}})


def test_common_prefix_cut_is_actual_cap_proof_not_last_job_completion():
    result={'first_cap_proofs_and_later_reads':{'A':{'after_api_ordinal':120},'B':{'after_api_ordinal':145}}}
    assert v.first_proof_count(result,200)==121


def test_passive_counter_restores_replay_and_helpers_on_failure(monkeypatch,tmp_path):
    before=(r.reference.base.ReplayTape,r.reference.physical_barrier,r.candidate.physical_barrier,r.reference.RepeatOwner)
    monkeypatch.setattr(r.reference.base,'read',lambda path:{'supply_cap':3,'parking_plan':{'token_tray_id':'t'}})
    def fail(directory):
        assert r.reference.base.ReplayTape is not before[0]
        assert r.reference.physical_barrier is r.candidate.physical_barrier
        raise ValueError('test_stop')
    monkeypatch.setattr(v,'verify_case_corrected',fail)
    with pytest.raises(ValueError,match='test_stop'):v.verified_counter(tmp_path,quiescent=True)
    assert before==(r.reference.base.ReplayTape,r.reference.physical_barrier,r.candidate.physical_barrier,r.reference.RepeatOwner)
