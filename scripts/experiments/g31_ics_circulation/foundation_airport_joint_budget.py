"""Locked single-runner accounting; interrupted intervals remain charged."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
from .foundation_airport_action_campaign import read, write, sha

SCHEMA = 'g31.joint_reposition_budget.v1'
ALLOCATIONS = dict(gates=8, bridge=20, initial=24, recollect=12, development=24, formal=64, reserve=8)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(cycle):
    # OS locks are automatically released on process exit; a stale file is safe.
    with (Path(cycle)/'.admission.lock').open('a+b') as stream:
        if not stream.tell():
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('joint_budget:admission_locked_by_another_process') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _identity():
    import psutil
    process = psutil.Process()
    return dict(pid=process.pid, process_created_at=process.create_time())


def _live(identity):
    import psutil
    if not identity.get('pid') or identity.get('process_created_at') is None:
        raise ValueError('joint_budget:runner_identity_missing_manual_audit_required')
    try:
        process = psutil.Process(identity['pid'])
        return process.create_time() == identity['process_created_at'] and process.is_running()
    except psutil.NoSuchProcess:
        return False


def _events(cycle):
    path=Path(cycle)/'ledger.jsonl'
    if not path.exists(): raise ValueError('joint_budget:registered_ledger_missing')
    try:
        return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line]
    except json.JSONDecodeError as error:
        raise ValueError('joint_budget:incomplete_ledger_requires_audit') from error


def events(cycle):
    with _locked(cycle): return _events(cycle)


def _append(cycle, kind, **fields):
    with (Path(cycle)/'ledger.jsonl').open('a',encoding='utf8') as stream:
        stream.write(json.dumps(dict(at=now(),event=kind,**fields),allow_nan=False)+'\n')
        stream.flush(); os.fsync(stream.fileno())


def _active(rows):
    active={}
    for row in rows:
        if row['event']=='runner_open':
            if active: raise ValueError('joint_budget:overlapping_runner_intervals')
            active[row['runner_id']]=row
        elif row['event']=='runner_close':
            if row['runner_id'] not in active: raise ValueError('joint_budget:runner_close_without_open')
            del active[row['runner_id']]
    return active


def _unfinished(rows):
    started = {}
    for row in rows:
        if row['event'] == 'native_start':
            if row['task_id'] in started:
                raise ValueError('joint_budget:duplicate_native_task')
            started[row['task_id']] = row
        elif row['event'] == 'native_finish':
            if row['task_id'] not in started:
                raise ValueError('joint_budget:native_finish_without_open_attempt')
            del started[row['task_id']]
    return started


def append(cycle, kind, **fields):
    with _locked(cycle):
        rows=_events(cycle); active=_active(rows)
        if kind=='runner_open':
            if active: raise ValueError('joint_budget:recover_existing_runner_first')
            if not fields.get('runner_id') or any(r.get('runner_id')==fields['runner_id'] for r in rows):
                raise ValueError('joint_budget:fresh_runner_identity_required')
            fields.update(_identity())
        elif kind=='runner_close':
            saved=active.get(fields.get('runner_id'))
            if saved is None or any(saved.get(k)!=v for k,v in _identity().items()):
                raise ValueError('joint_budget:runner_close_requires_own_process')
        elif kind=='native_start':
            raise ValueError('joint_budget:native_start_requires_admit')
        elif kind=='native_finish':
            attempt = _unfinished(rows).get(fields.get('task_id'))
            if attempt is None or attempt['runner_id'] not in active:
                raise ValueError('joint_budget:native_finish_requires_active_attempt')
            if any(active[attempt['runner_id']].get(k) != v for k,v in _identity().items()):
                raise ValueError('joint_budget:native_finish_requires_own_process')
        _append(cycle,kind,**fields)


def recover_runner(cycle, runner_id, *, reason):
    """Explicitly close a verified dead runner, charging through recovery time."""
    if not isinstance(reason,str) or not reason.strip():
        raise ValueError('joint_budget:explicit_recovery_reason_required')
    with _locked(cycle):
        saved=_active(_events(cycle)).get(runner_id)
        if saved is None: raise ValueError('joint_budget:runner_not_open')
        if _live(saved): raise ValueError('joint_budget:cannot_recover_live_runner')
        _append(cycle,'runner_close',runner_id=runner_id,recovered=True,
            recovery_reason=reason,previous_pid=saved['pid'])
    return status(cycle)


def recover_attempt(cycle, task_id, *, reason):
    """Retain a dead runner's unresolved attempt as unknown; never refund it."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('joint_budget:explicit_recovery_reason_required')
    with _locked(cycle):
        rows = _events(cycle); attempt = _unfinished(rows).get(task_id)
        if attempt is None:
            raise ValueError('joint_budget:attempt_not_open')
        saved = next(row for row in rows if row['event'] == 'runner_open'
            and row['runner_id'] == attempt['runner_id'])
        if _live(saved):
            raise ValueError('joint_budget:cannot_recover_live_runner')
        _append(cycle, 'native_finish', task_id=task_id, recovered=True,
            process_status='interrupted_unknown', scientific_status='unknown_unclosed_attempt',
            recovery_reason=reason)
    return status(cycle)


def register(cycle, plan_path, anchor):
    cycle=Path(cycle); cycle.mkdir(parents=True,exist_ok=True)
    with _locked(cycle):
        path=cycle/'campaign_budget.json'
        if path.exists():
            result=read(path)
            if result['plan_sha256']!=sha(plan_path) or result['anchor_commit']!=anchor:
                raise ValueError('joint_budget:registration_conflict')
            _events(cycle)
            return result
        if (cycle/'ledger.jsonl').exists(): raise ValueError('joint_budget:orphan_ledger_requires_audit')
        result=dict(schema=SCHEMA,registered_at_utc=now(),plan_sha256=sha(plan_path),anchor_commit=anchor,
            native_start_limit=160,allocations=dict(ALLOCATIONS),active_seconds_limit=48*3600,
            new_evidence_bytes_limit=40*1024**3,free_space_floor_bytes=30*1024**3,initial_native_concurrency=1,
            active_time_definition='sum of durable active runner intervals; no reset on resume; open interval conservatively charged until explicit recovery',
            calendar_time_accounted_separately=True,paused_intervals_excluded_only_with_explicit_closed_runner_interval=True,
            failed_start_counts=True,test_locked=True)
        (cycle/'ledger.jsonl').touch(exist_ok=False); write(path,result)
        return result


def _status(cycle):
    cycle=Path(cycle); b=read(cycle/'campaign_budget.json'); rows=_events(cycle)
    starts=[r for r in rows if r['event']=='native_start']; _active(rows)
    active={}; elapsed=0.; instant=datetime.now(timezone.utc)
    for row in rows:
        if row['event']=='runner_open': active[row['runner_id']]=datetime.fromisoformat(row['at'])
        elif row['event']=='runner_close':
            duration=(datetime.fromisoformat(row['at'])-active.pop(row['runner_id'])).total_seconds()
            if duration<0: raise ValueError('joint_budget:runner_clock_regression')
            elapsed+=duration
    durations=[(instant-t).total_seconds() for t in active.values()]
    if any(d<0 for d in durations): raise ValueError('joint_budget:runner_clock_regression')
    elapsed+=sum(durations)
    return dict(native_starts=len(starts),by_batch={k:sum(r['batch']==k for r in starts) for k in b['allocations']},
        active_seconds=elapsed,open_runners=list(active),unfinished_native_tasks=list(_unfinished(rows)),
        evidence_bytes=sum(p.stat().st_size for p in cycle.rglob('*') if p.is_file()),
        free_bytes=shutil.disk_usage(cycle).free,
        calendar_seconds=(instant-datetime.fromisoformat(b['registered_at_utc'])).total_seconds())


def status(cycle):
    with _locked(cycle): return _status(cycle)


def admit(cycle, plan):
    with _locked(cycle):
        b=read(Path(cycle)/'campaign_budget.json'); s=_status(cycle); rows=_events(cycle); active=_active(rows)
        if len(active)!=1 or any(next(iter(active.values())).get(k)!=v for k,v in _identity().items()):
            raise ValueError('joint_budget:owned_active_runner_required')
        if _unfinished(rows):
            raise ValueError('joint_budget:unfinished_native_attempt_requires_audit')
        if (not isinstance(plan.get('task_id'),str) or not plan['task_id'] or plan.get('batch') not in b['allocations']
                or type(plan.get('hard_seconds')) not in (int,float)
                or not math.isfinite(plan['hard_seconds']) or plan['hard_seconds']<=0):
            raise ValueError('joint_budget:invalid_task_admission')
        if plan.get('parent',{}).get('split')=='test' and b['test_locked']:
            raise ValueError('joint_budget:formal_locked')
        if s['native_starts']>=b['native_start_limit'] or s['by_batch'][plan['batch']]>=b['allocations'][plan['batch']]:
            raise ValueError('joint_budget:native_allocation_exhausted')
        if s['active_seconds']+plan['hard_seconds']>b['active_seconds_limit']:
            raise ValueError('joint_budget:active_time_exhausted')
        estimate=plan.get('estimated_evidence_bytes',0)
        if type(estimate) is not int or estimate<0: raise ValueError('joint_budget:invalid_evidence_estimate')
        if s['evidence_bytes']+estimate>=b['new_evidence_bytes_limit'] or s['free_bytes']-estimate<b['free_space_floor_bytes']:
            raise ValueError('joint_budget:disk_boundary')
        if any(r.get('task_id')==plan['task_id'] and r['event']=='native_start' for r in rows):
            raise ValueError('joint_budget:no_silent_task_relaunch')
        _append(cycle,'native_start',task_id=plan['task_id'],batch=plan['batch'],runner_id=next(iter(active)),
            plan_sha256=plan['plan_sha256'],binary_sha256=plan['binary']['sha256'],
            source_manifest_sha256=plan['source_bundle']['sha256'])
