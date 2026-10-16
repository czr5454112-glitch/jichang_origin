from copy import deepcopy
import json
import shutil
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_original_bridge_serialize_once as r
from scripts.experiments.g31_ics_circulation import verify_original_bridge_serialize_once as v
from scripts.experiments.g31_ics_circulation import launch_original_bridge_serialize_once as launch


def test_measurement_MRO_preserves_exact_old_methods_and_selects_new_tape(tmp_path,monkeypatch):
    cls=r.MeasuredSerializedTape;old=r.original.MeasuredTape;new=r.tape_candidate.SerializedOnceTape
    assert cls.__mro__[:4]==(cls,old,new,r.base.Tape)
    assert cls.__init__ is old.__init__ and cls.__getattr__ is old.__getattr__ and cls.clock is old.clock
    calls=[];write=r.tape_candidate.write_row
    monkeypatch.setattr(r.tape_candidate,'write_row',lambda *args:(calls.append(args[0]),write(*args))[1])
    class Session:
        physical_time=1.
        def protocol_request(self,*args):return {'last_delivered_ack':{'status':'received'}}
    tape=cls(Session(),tmp_path/'api');result=tape.protocol_request('A','opaque')
    assert len(calls)==1 and result['last_delivered_ack']['status']=='received'
    clocks=[json.loads(line) for line in tape.clock_path.read_text().splitlines()]
    assert len(clocks)==1 and clocks[0]['scope']=='complete_frozen_api_and_tape_write'
    assert clocks[0]['ordinal']==0 and tape.api_persisted_bytes>0


def test_private_worker_campaign_and_policy_code_exact_no_old_globals_changed():
    old=dict(vars(r.original));base_before=dict(vars(r.base));ns=r.runner_namespace();p=ns['isolated_base']()
    for name in ('worker','measured_run','isolated_base','prepare','campaign_worker','verify_campaign'):
        assert ns[name].__code__ is getattr(r.original,name).__code__ and ns[name].__globals__ is ns
    assert p.worker.__code__ is r.base.worker.__code__
    assert p.verify_saved.__code__ is r.base.verify_saved.__code__
    assert p.worker.__globals__['Tape'] is r.MeasuredSerializedTape
    assert p.worker.__globals__['run_policy'] is r.policy.run_policy
    assert p.HORIZON==86400 and p.MAX_PHYSICAL==100
    assert ns['measured_run'].__globals__['policy'].BridgeOwner is r.policy.BridgeOwner
    assert vars(r.original)==old and vars(r.base)==base_before


def test_verifier_keeps_all_original_code_and_injects_only_offline_observer():
    comparison=SimpleNamespace(consume=lambda row:None)
    replay=v.compared_replay_type(comparison);function=v.verifier_function(replay)
    assert replay.__getattr__.__code__ is r.base.ReplayTape.__getattr__.__code__
    assert function.__code__ is v.original.verify_case.__code__
    assert function.__globals__['base'].ReplayTape is replay
    assert function.__globals__['r'].policy.BridgeOwner is r.policy.BridgeOwner
    assert function.__globals__['physical_outcomes'] is v.original.physical_outcomes
    assert function.__globals__['validate_clocks'] is v.original.validate_clocks


def test_launcher_preserves_owned_job_budget_cleanup_and_internal_gate_code():
    before=dict(vars(launch.original));ns=launch.launcher_namespace()
    for name in ('main','validate_internal','retained_evidence'):
        assert ns[name].__code__ is getattr(launch.original,name).__code__ and ns[name].__globals__ is ns
    assert ns['LIMIT']==r.LIMIT==2400 and ns['MODULE']==r.MODULE and ns['SCHEMA']==r.SCHEMA
    assert ns['bounded_windows_job'] is launch.original.bounded_windows_job and vars(launch.original)==before


def make_prefix(tmp_path):
    directory=tmp_path/'old';directory.mkdir()
    rows=[dict(ordinal=0,endpoint='protocol_request',args=['A','r'],kwargs={},before=0.,result={'a':1,'b':2},after=0.),
        dict(ordinal=1,endpoint='advance_to',args=[10.],kwargs={},before=0.,result={'wall_seconds':.1,'horizon_complete':True},after=10.)]
    manifest=[]
    for row in rows:
        path=directory/f"{row['ordinal']:06d}.json.gz";r.base.gzwrite(path,row)
        manifest.append({'path':path.name,'sha256':r.base.sha(path),'endpoint':row['endpoint']})
    path=directory/'manifest.jsonl';path.write_text(''.join(json.dumps(x)+'\n' for x in manifest))
    return directory,r.base.sha(path),rows


def test_prefix_exact_ordered_data_only_declared_finite_wall_excluded(tmp_path):
    directory,digest,rows=make_prefix(tmp_path);old=deepcopy(rows)
    comparison=v.PrefixComparison(directory,digest,2)
    rows[1]['result']['wall_seconds']=2.
    for row in rows:comparison.consume(row)
    assert comparison.finish()['rows']==2
    assert v.semantic_api(rows[1])==v.original.semantic_api(rows[1])
    assert rows[0]==old[0] and rows[1]['result']['wall_seconds']==2.
    # The old hard-killed last file is never silently decoded or repaired.
    (directory/'000002.json.gz').write_bytes(b'truncated')
    assert v.PrefixComparison(directory,digest,2).manifest==comparison.manifest


@pytest.mark.parametrize('tamper',['field','order','arg','owner','logical','nanwall','negativewall','boolwall','wall_elsewhere','gap'])
def test_changed_semantics_or_unsupported_wall_never_normalized(tmp_path,tamper):
    directory,digest,rows=make_prefix(tmp_path);comparison=v.PrefixComparison(directory,digest,2)
    if tamper=='field':rows[0]['result']['a']=9
    elif tamper=='order':rows[0]['result']={'b':2,'a':1}
    elif tamper=='arg':rows[0]['args'][1]='other'
    elif tamper=='owner':rows[0]['args'][0]='B'
    elif tamper=='logical':rows[0]['after']=1.
    elif tamper=='wall_elsewhere':rows[0]['result']['wall_seconds']=1.
    elif tamper=='gap':rows[0]['ordinal']=1
    else:rows[1]['result']['wall_seconds']={'nanwall':float('nan'),'negativewall':-1.,'boolwall':True}[tamper]
    with pytest.raises((ValueError,TypeError)):
        for row in rows:comparison.consume(row)
        comparison.finish()


def test_prefix_missing_row_or_changed_file_hash_is_unknown(tmp_path):
    directory,digest,rows=make_prefix(tmp_path);comparison=v.PrefixComparison(directory,digest,2)
    comparison.consume(rows[0])
    with pytest.raises(ValueError,match='incomplete_comparison'):comparison.finish()
    (directory/'000001.json.gz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='old_row_changed'):comparison.consume(rows[1])


def test_actual005_H20_prefix_executes_same_BridgeOwner_via_new_measured_tape(tmp_path):
    old=r.OUT/'original_low_wip_prepare_005';plan=r.base.read(old/'preregistered_protocol.json')
    manifest=[json.loads(line) for line in (old/'api/manifest.jsonl').read_text().splitlines()]
    source=tmp_path/'source';source.mkdir();entries=[]
    for entry in manifest:
        row=r.base.gzread(old/'api'/entry['path'])
        if row['endpoint']=='advance_to' and row['before']==20.:break
        shutil.copyfile(old/'api'/entry['path'],source/entry['path']);entries.append(entry)
    assert row['before']==20.
    (source/'manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in entries))
    session=r.base.ReplayTape(source);tape=r.MeasuredSerializedTape(session,tmp_path/'api');owners_seen=[]
    class ActualOwner(r.policy.BridgeOwner):
        def activate(self):owners_seen.append(self);return super().activate()
    run=r.original.clone(r.policy.run_policy,{**r.policy.run_policy.__globals__,'BridgeOwner':ActualOwner,'HORIZON':20.,'MAX_TICKS':3})
    owners,status,tick=run(tape,plan)
    assert status=='horizon_complete' and len(tape.rows)==session.index==len(entries)
    assert owners_seen and all(isinstance(o,r.policy.BridgeOwner) for o in owners_seen)
    comparison=v.PrefixComparison(source,r.base.sha(source/'manifest.jsonl'),len(entries))
    for meta in tape.rows:comparison.consume(r.base.gzread(tape.directory/meta['path']))
    assert comparison.finish()['last_logical_time']==20.


def test_reference_scope_and_new_source_dependency_inventory():
    old=r.reference_pins();scope=r.contract()
    assert old['horizon']==scope['horizon']==86400 and scope['offered']==28506 and scope['total_tray_identities']==22
    assert (scope['max_actual_token_completions'],scope['max_postparking_empty_operations'],scope['max_physical_requests'])==(39,78,100)
    paths={p.name for p in r.source_paths()}
    assert {'research_original_bridge_serialize_once.py','verify_original_bridge_serialize_once.py',
        'launch_original_bridge_serialize_once.py','serialize_once_low_wip_tape.py','bounded_windows_job.py',
        'cooperative_bridge_policy.py','current_empty_possession_permit.py',
        'test_g31_circulation_bridge_serialize_once.py'}<=paths


def test_duplicate_preparation_never_overwrites_old_evidence(tmp_path):
    (tmp_path/'sentinel').write_text('original')
    with pytest.raises(ValueError,match='preserve_output'):r.prepare(tmp_path,tmp_path/'unused.xml')
    assert (tmp_path/'sentinel').read_text()=='original'
