import copy
import time

import pytest

from scripts.experiments.g31_ics_circulation import run_sustained_learning as run


def ledger(tmp_path):
    path=tmp_path/'manifest.json'
    run.initialize(path,{'schema':run.SCHEMA,'max_native_branches':120,'max_native_per_task':12,
        'native_parallelism':1,'started_utc_epoch':time.time(),'deadline_utc_epoch':time.time()+1000})
    return path


def spec(identity='a',native=2):
    return {'task_id':identity,'module':'scripts.experiments.g31_ics_circulation.example',
            'args':[],'sources':[str(run.__file__)],'native_branches':native,'hard_seconds':10}


def test_reservation_charged_before_work_and_never_automatically_retried(tmp_path):
    path=ledger(tmp_path);run.register(path,spec());task,output=run.reserve(path,'a')
    assert run.read(path)['native_branches_reserved']==2
    assert (output/'registration.json').is_file()
    with pytest.raises(ValueError,match='already_attempted'):
        run.reserve(path,'a')
    run.finish(path,'a',{'status':'failed','reason':'known failure'})
    with pytest.raises(ValueError,match='already_attempted'):
        run.reserve(path,'a')
    assert run.read(path)['native_branches_reserved']==2


def test_running_attempt_blocks_duplicate_collector(tmp_path):
    path=ledger(tmp_path);run.register(path,spec());run.register(path,spec('b'))
    run.reserve(path,'a')
    with pytest.raises(ValueError,match='existing_attempt'):
        run.reserve(path,'b')


def test_registration_rejects_oversized_native_batch(tmp_path):
    path=ledger(tmp_path)
    with pytest.raises(ValueError,match='task_native_budget'):
        run.register(path,spec(native=13))


def test_missing_budget_stops_before_reservation(tmp_path):
    path=ledger(tmp_path);run.register(path,spec())
    state=run.read(path);state['native_branches_reserved']=119;run.atomic(path,state)
    with pytest.raises(ValueError,match='native_budget_exhausted'):
        run.reserve(path,'a')
    assert run.read(path)['tasks']['a']['status']=='prepared'


def test_expired_cycle_stops_before_launch(tmp_path):
    path=ledger(tmp_path);run.register(path,spec())
    state=run.read(path);state['deadline_utc_epoch']=time.time()-1;run.atomic(path,state)
    with pytest.raises(ValueError,match='remaining_wall'):
        run.reserve(path,'a')


def test_changed_source_cannot_repin_prepared_task(tmp_path):
    path=ledger(tmp_path);run.register(path,spec())
    state=run.read(path);state['tasks']['a']['source_pins'][str(run.__file__)]= '0'*64;run.atomic(path,state)
    with pytest.raises(ValueError,match='source_changed'):
        run.reserve(path,'a')


def test_existing_lock_is_not_silently_deleted(tmp_path):
    path=ledger(tmp_path); lock=tmp_path/'manifest.json.lock';lock.write_text('unknown pid')
    with pytest.raises(FileExistsError):
        run.register(path,spec())
    assert lock.read_text()=='unknown pid'
