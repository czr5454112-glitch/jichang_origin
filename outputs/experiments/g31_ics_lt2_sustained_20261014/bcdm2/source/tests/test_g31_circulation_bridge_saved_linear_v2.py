"""No real saved artifact reads, models or native execution in this pure gate."""
from copy import deepcopy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_saved_linear_progress_v2 as c
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_linear_v2 as a


def records(progress):
    return [json.loads(line) for line in progress.path.read_text(encoding='utf8').splitlines()]


def test_complete_bootstrap_and_full_campaign_progress_below_original_limit(tmp_path,monkeypatch):
    # Complete old005 bootstrap reference has10305 rows; this exercises every
    # possible row plus its whole raw, not only the actual shorter prefix.
    progress=c.Progress(tmp_path);loaded=[]
    def loader(path):loaded.append(path);return {'value':[len(loaded)]}
    shared=c.SharedReads(tmp_path,progress,loader)
    for name in ('raw_final.json.gz','input.json.gz'):
        first=shared.read(tmp_path/name)
        assert shared.read(tmp_path/name) is first
    shared.read(tmp_path/'bootstrap/raw_final.json.gz')
    # Synthetic missing paths must not spend the pure gate doing10305 Windows
    # filesystem-resolution probes. All are already absolute; only this count
    # simulation stubs resolve. Real resolution is covered by the small tests.
    with monkeypatch.context() as patch:
        patch.setattr(Path,'resolve',lambda path:path)
        for i in range(10305):shared.read(tmp_path/'bootstrap/api'/f'{i:06d}.json.gz')
    assert shared.other_reads==10306 and len(loaded)==10308
    assert len(shared.values)==len(shared.requests)==len(shared.decodes)==2
    assert len(shared.finish())==2
    for i in range(1,37271):
        if i%256==0:
            progress.emit('new_row_hash_progress',completed=i)
            progress.emit('api_replay_progress',completed=i)
    # Reserve128 additional fixed nonrow events, well beyond this fixed
    # original call graph; neither this reserve nor1024 is increased at runtime.
    for i in range(128):progress.emit('fixed_phase_reserve',index=i)
    progress.close(); rows=records(progress)
    assert len(rows)==465 < 1024 and c.Progress.LIMIT==1024
    assert len([r for r in rows if r['event']=='stage_start'])==2
    assert len([r for r in rows if r['event']=='bootstrap_other_read_progress'])==40
    assert [r['record'] for r in rows]==list(range(465))


def test_more_than600_reads_have_no_per_row_stages_or_cache(tmp_path,monkeypatch):
    progress=c.Progress(tmp_path);calls=[]
    shared=c.SharedReads(tmp_path,progress,lambda path:calls.append(path) or {'read':len(calls)})
    path=tmp_path/'other/api.json.gz'
    with monkeypatch.context() as patch:
        patch.setattr(Path,'resolve',lambda path:path)
        values=[shared.read(path) for _ in range(700)]
    assert [v['read'] for v in values]==list(range(1,701))
    assert len(calls)==700 and shared.values=={} and shared.requests=={} and shared.decodes=={}
    progress.close();rows=records(progress)
    assert [r['event'] for r in rows]==['bootstrap_other_read_progress']*2
    assert [r['completed'] for r in rows]==[256,512]


def test_allowed_reads_keep_identity_and_two_read_denominator(tmp_path):
    p=c.Progress(tmp_path);s=c.SharedReads(tmp_path,p,lambda path:{'path':path.name})
    raw=s.read(tmp_path/'raw_final.json.gz')
    assert s.read(tmp_path/'raw_final.json.gz') is raw
    with pytest.raises(ValueError,match='denominator'):s.finish()
    data=s.read(tmp_path/'input.json.gz');assert s.read(tmp_path/'input.json.gz') is data
    assert len(s.finish())==2
    s.read(tmp_path/'input.json.gz')
    with pytest.raises(ValueError,match='denominator'):s.finish()
    p.close()


def test_ordinary_loader_error_is_not_counted_or_converted(tmp_path):
    p=c.Progress(tmp_path);failure=OSError('actual loader failed')
    def bad(path):raise failure
    s=c.SharedReads(tmp_path,p,bad)
    with pytest.raises(OSError) as caught:s.read(tmp_path/'other.json.gz')
    assert caught.value is failure and s.other_reads==0 and p.first_failure is None
    p.close()


def test_capacity_first_error_sticky_even_after_policy_swallow_and_secondary_order_error(tmp_path):
    p=c.Progress(tmp_path);p.LIMIT=1
    secondary=ValueError('serialize_bridge_prefix_order')
    with pytest.raises(ValueError,match='linear_progress_budget') as caught:
        with p.stage('complete_policy_replay'):
            try:p.emit('second')
            except ValueError:pass  # Exact exception family caught by the policy.
            raise secondary
    assert caught.value is p.first_error and caught.value.__cause__ is secondary
    assert p.failed and p.first_failure['event']=='second' and p.first_failure['record_count']==1
    with pytest.raises(ValueError) as repeated:p.emit('third')
    assert repeated.value is caught.value
    with pytest.raises(ValueError):p.close()
    assert p.stream.closed and len(records(p))==1


@pytest.mark.parametrize('method',['write','flush','short_write'])
def test_io_failure_sticky_and_shared_reads_stop_before_next_loader(tmp_path,method):
    p=c.Progress(tmp_path);p.stream.close();failure=OSError('first '+method);closed=[]
    class Stream:
        def write(self,text):
            if method=='write':raise failure
            return 0 if method=='short_write' else len(text)
        def flush(self):
            if method=='flush':raise failure
        def close(self):closed.append(True)
    p.stream=Stream()
    with pytest.raises((ValueError,OSError)) as caught:p.emit('record')
    first=caught.value;calls=[];s=c.SharedReads(tmp_path,p,lambda path:calls.append(path))
    with pytest.raises(type(first)) as again:s.read(tmp_path/'other.json.gz')
    assert again.value is first and calls==[]
    with pytest.raises(type(first)):p.close()
    assert closed==[True] and p.first_error is first


def test_nested_original_checker_error_keeps_priority_when_failure_logging_also_breaks(tmp_path):
    p=c.Progress(tmp_path);p.LIMIT=2;original=RuntimeError('real checksum failure')
    with pytest.raises(RuntimeError) as caught:
        with p.stage('outer'):
            with p.stage('inner'):raise original
    assert caught.value is original and p.reporting_original_error is original
    assert p.first_failure['event']=='stage_failed'
    with pytest.raises(ValueError):p.close()


def test_final_flush_always_closes_and_preserves_first_error(tmp_path):
    p=c.Progress(tmp_path);p.stream.close();first=OSError('firstflush');closed=[]
    class Stream:
        def flush(self):raise first
        def close(self):closed.append(True);raise RuntimeError('secondclose')
    p.stream=Stream()
    with pytest.raises(OSError) as caught:p.close()
    assert caught.value is first and closed==[True] and p.closed
    assert p.first_failure['event']=='close_flush'


def test_successful_close_and_oversize_row_failure_do_not_certify_later_success(tmp_path):
    p=c.Progress(tmp_path);p.emit('ok');p.close();p.close()
    with pytest.raises(ValueError):p.emit('after_close')
    other=tmp_path/'other';other.mkdir();q=c.Progress(other)
    with pytest.raises(ValueError,match='row_limit'):q.emit('large',value='x'*5000)
    assert q.count==0 and q.first_failure['event']=='large'
    with pytest.raises(ValueError):q.close()


def test_private_bind_has_identical_checker_and_actor_copy_semantics(tmp_path,monkeypatch):
    reference=tmp_path/'reference';directory=reference/'bridge/api';directory.mkdir(parents=True)
    manifest=directory/'manifest.jsonl';manifest.write_text('')
    monkeypatch.setattr(c.r,'REFERENCE',reference);monkeypatch.setattr(c.r,'PREFIX_ROWS',0)
    monkeypatch.setattr(c.r,'MANIFEST_SHA',c.base.sha(manifest))
    source=tmp_path/'source';(source/'bridge').mkdir(parents=True);output=tmp_path/'new';output.mkdir()
    redirect=a.prior.DerivedOutput(source,output);p=c.Progress(output)
    execute=c.bind({'source_before':{}},redirect,p)
    captured=dict(zip(execute.__code__.co_freevars,(x.cell_contents for x in execute.__closure__)))
    assert type(captured['shared']) is c.SharedReads
    original=c.old.bind({'source_before':{}},redirect,p)
    oldcells=dict(zip(original.__code__.co_freevars,(x.cell_contents for x in original.__closure__)))
    assert execute.__code__ is original.__code__
    assert captured['checker'].__code__.co_code==oldcells['checker'].__code__.co_code
    assert captured['ast_proofs']==oldcells['ast_proofs']
    p.close()


def test_driver_private_namespace_keeps_budget_guards_and_no_old_global_mutation():
    before=dict(vars(a.old));ns=a.namespace()
    assert vars(a.old)==before and ns['MODULE']==a.MODULE and ns['core'] is c
    assert ns['namespace'] is a.namespace and ns['contract'] is a.contract
    assert ns['PRIOR']==a.old.PRIOR and ns['PRIOR_PLAN_SHA']==a.old.PRIOR_PLAN_SHA
    assert a.LIMIT==600 and a.prior.LIMIT==600 and c.Progress.LIMIT==1024
    assert 'terminal_refs(' not in inspect.getsource(a.prepare)
    assert 'NativeSession' not in inspect.getsource(a.audit)


def test_driver_retains_bounded_first_fatal_sidecar(tmp_path,monkeypatch):
    def fake(output,expected):
        progress=core.Progress(output);progress.LIMIT=1
        try:
            with progress.stage('policy'):
                try:progress.emit('fatal')
                except ValueError:pass
                raise ValueError('later_prefix_order')
        finally:
            try:progress.close()
            except ValueError:pass
    monkeypatch.setattr(a.old,'audit',fake)
    with pytest.raises(ValueError,match='linear_progress_budget'):a.audit(tmp_path,'x')
    saved=json.loads((tmp_path/'instrumentation_failure.json').read_text())
    assert saved['first_progress_failure']['event']=='fatal'
    assert saved['complete_saved_audit'] is False and saved['journal_rows_committed']==1
    assert 'linear_progress_budget' in saved['terminal_exception']


def test_progress_contract_does_not_expand_limit_or_remove_reads():
    value=c.progress_contract()
    assert value['record_limit']==1024 and value['row_interval']==256
    assert value['individual_decode_stages']==['raw_final.json.gz','input.json.gz']
    assert 'Every original read still happens' in value['other_reads']
