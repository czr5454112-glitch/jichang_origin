from __future__ import annotations
import copy
import hashlib
import io
import json
from pathlib import Path
import queue
import sys
import time
import pytest
from scripts.experiments.g31_ics_circulation import json_prediction_image as codec
from scripts.experiments.g31_ics_circulation import json_prediction_worker as worker
from scripts.experiments.g31_ics_circulation import json_prediction_client as client
from scripts.experiments.g31_ics_circulation import public_preference_protection_request_context as original

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_static_context_pair_001/worker/supplied_inputs.json'
INPUT_SHA = '0066994f93a7a25a8aa0a005020bb262909d5c4c5aacbfea5e14bbb2b262b0cb'


def inputs():
    data = INPUT.read_bytes()
    assert hashlib.sha256(data).hexdigest() == INPUT_SHA
    return [row for row in json.loads(data) if row['owner'] == 'A']


def old(snapshot):
    context = original.ProtectionRequestContext(snapshot)
    actions = context.actions()
    return {'baseline': context.baseline(), 'actions': actions,
            'predictions': [context.predict(action) for action in actions]}


@pytest.fixture(scope='module')
def compiled():
    return worker.Engine('compiled')


@pytest.fixture(scope='module')
def frozen_image(tmp_path_factory):
    folder = tmp_path_factory.mktemp('json_worker')/'image'
    return folder, codec.build_image(ROOT, folder)


@pytest.mark.parametrize('index', range(6))
def test_exact_six_actual_inputs_all32_full_and_partial(index, compiled):
    snapshot = codec.decode(codec.encode(inputs()[index]['bundle']))
    expected, actual = old(snapshot), compiled.predict(snapshot)
    assert len(actual['actions']) == len(actual['predictions']) == 32
    assert codec.encode(actual) == codec.encode(expected)
    assert set(compiled.__dict__) == {'mode', 'context', 'proof'}


def test_A_B_A_mutations_and_no_retained_potential_or_label(compiled):
    first, second = inputs()[0]['bundle'], inputs()[5]['bundle']
    expected = compiled.predict(first)
    mutable = compiled.predict(first)
    mutable['baseline']['completion'].clear()
    mutable['actions'][0].clear()
    compiled.predict(second)
    assert codec.encode(compiled.predict(first)) == codec.encode(expected)
    assert compiled.proof['guard_compilations'] == 1


@pytest.mark.parametrize('defect', ['status', 'pending', 'resource', 'generation', 'job', 'missing'])
def test_every_request_dynamic_guards_and_unknown_recovery(compiled, defect):
    value = copy.deepcopy(inputs()[0]['bundle'])
    if defect == 'status': value['status'] = 'unknown'
    elif defect == 'pending': value['owner_pending_tray_requests'] = ['pending']
    elif defect == 'resource': value['resources']['0']['occupancy'] += 1
    elif defect == 'generation': value['trays']['L']['generation'] = False
    elif defect == 'job': value['jobs']['loaded']['loaded_at'] = .2
    else: value['jobs'].pop('receiver')
    assert codec.encode(compiled.predict(value)) == codec.encode(old(value))
    assert len(compiled.predict(inputs()[1]['bundle'])['predictions']) == 32


def test_no_per_request_source_inventory_or_compile(compiled, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('startup work repeated')
    monkeypatch.setattr(original.base, 'compile_guards', forbidden)
    monkeypatch.setattr(original.proof, 'source_proof', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    # Input already decoded before the startup-only calls are disabled.
    snapshot = json.loads(INPUT.read_text(encoding='utf8'))[0]['bundle']
    assert len(compiled.predict(snapshot)['predictions']) == 32


def test_original_functions_and_modules_not_patched():
    before = (original.base.RequestContext.__init__, original.base.compile_guards,
              original.ProtectionRequestContext.__init__, original.proof.source_proof,
              original.base.original.Projection.__init__, original.base.original.Projection.run)
    worker.Engine('compiled')
    after = (original.base.RequestContext.__init__, original.base.compile_guards,
             original.ProtectionRequestContext.__init__, original.proof.source_proof,
             original.base.original.Projection.__init__, original.base.original.Projection.run)
    assert before == after


def test_changed_in_memory_proof_rejected_at_startup(monkeypatch):
    monkeypatch.setattr(original.base.original.Projection, 'run', lambda self: {})
    with pytest.raises(ValueError, match='changed_proof_function'):
        worker.Engine('compiled')


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{"a":1e999}\n',
    b'{"a":Infinity}\n', b'{"a":-Infinity}\n', b'{}', b'{}\n{}\n', b'\xef\xbb\xbf{}\n', b'"\xff"\n'])
def test_strict_json_rejections(raw):
    with pytest.raises((ValueError, UnicodeError)):
        codec.decode(raw)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), {1: 2}, (1, 2), object()])
def test_no_non_json_or_reducer_domain(value):
    with pytest.raises(ValueError): codec.encode(value)


def test_UTF8_order_numeric_types_negative_zero_and_fresh_decoding():
    value = {'字': -0.0, 'x': [1, 1.0, True, '\n']}
    raw = codec.encode(value)
    assert codec.encode(codec.decode(raw)) == raw
    assert list(codec.decode(raw)) == ['字', 'x']
    result = codec.decode(raw); result['x'].append(0)
    assert len(codec.decode(raw)['x']) == 4


def test_frame_depth_and_node_limits(monkeypatch):
    monkeypatch.setattr(codec, 'MAX_FRAME_BYTES', 5)
    with pytest.raises(ValueError): codec.encode({'a': 1})
    with pytest.raises(ValueError): codec.read_frame(io.BytesIO(b'{"a":1}\n'))
    monkeypatch.setattr(codec, 'MAX_FRAME_BYTES', 1000)
    monkeypatch.setattr(codec, 'MAX_DEPTH', 2)
    with pytest.raises(ValueError): codec.encode([[[[1]]]])
    monkeypatch.setattr(codec, 'MAX_NODES', 2)
    with pytest.raises(ValueError): codec.encode([1, 2])


class FakeEngine:
    def predict(self, snapshot): return {'snapshot': copy.deepcopy(snapshot)}


def request(**changes):
    return {'kind': 'predict', 'version': 'v', 'sequence': 1, 'request_id': 'r1', 'snapshot': {}, **changes}


@pytest.mark.parametrize('changes', [{'version':'old'}, {'sequence':True}, {'sequence':2},
    {'request_id':''}, {'kind':'exec'}, {'snapshot':[]}, {'exec':'x'}, {'baseline_completion':{}}])
def test_protocol_closed_schema_and_version(changes):
    with pytest.raises(ValueError): worker.Protocol('v', FakeEngine(), codec).accept(request(**changes))


def test_replay_identity_capacity_and_close(monkeypatch):
    protocol = worker.Protocol('v', FakeEngine(), codec)
    protocol.accept(request())
    with pytest.raises(ValueError): protocol.accept(request(sequence=2))
    with pytest.raises(ValueError): protocol.accept(request(request_id='r2'))
    monkeypatch.setattr(codec, 'MAX_REQUESTS', 1)
    with pytest.raises(ValueError): protocol.accept(request(sequence=2,request_id='r2'))
    assert protocol.accept({'kind':'close','version':'v','sequence':2}) is None
    with pytest.raises(ValueError): protocol.accept(request(sequence=2,request_id='r2'))


def test_EOF_and_predict_exception_do_not_forge_closed():
    output = io.BytesIO()
    with pytest.raises(ValueError, match='EOF_without_close'):
        worker.serve(io.BytesIO(b''), output, 'v', FakeEngine(), codec, lambda: True)
    assert output.getvalue() == b''
    class Bad:
        def predict(self, snapshot): raise RuntimeError('model_failed')
    with pytest.raises(RuntimeError, match='model_failed'):
        worker.serve(io.BytesIO(codec.encode(request())), output, 'v', Bad(), codec, lambda: True)
    assert output.getvalue() == b''


def test_source_image_versions_and_changes(tmp_path):
    folder = tmp_path/'image'; version = codec.build_image(ROOT, folder)
    manifest, files = codec.verify_image(folder, version)
    assert 'scripts/eval/run_g4irsf28_service_potential.py' in files
    assert 'src/czr005/cpp_backend.py' in files
    assert 'scripts/experiments/g31_ics_circulation/json_prediction_image.py' in files
    with pytest.raises(ValueError, match='version'): codec.verify_image(folder, '0'*64)
    target = folder/next(iter(files)); target.write_bytes(target.read_bytes()+b'\n')
    with pytest.raises(ValueError, match='source_bytes'): codec.verify_image(folder, version)
    (folder/'added.py').write_text('x=1\n')
    target.write_bytes(files[next(iter(files))])
    with pytest.raises(ValueError, match='unlisted_source'): codec.verify_image(folder, version)


def test_immutable_loader_uses_verified_bytes_and_refuses_late_import(tmp_path):
    loader = codec.ImageLoader(tmp_path, {'scripts/new.py': b'x=1\n'})
    assert loader.find_spec('scripts.new') is not None
    loader.sealed = True
    with pytest.raises(ImportError, match='after_READY'): loader.find_spec('scripts.new')
    assert loader.find_spec('json') is None


def test_actual_isolated_JSON_child_exact_case_and_changed_input(frozen_image, tmp_path):
    folder, version = frozen_image
    with (tmp_path/'stderr.log').open('wb') as errors:
        with client.Client(folder, version, 'compiled', timeout=30., stderr=errors) as rpc:
            assert rpc.ready['proof']['guard_compilations'] == 1
            assert rpc.ready['loaded_sources']
            for n, source in enumerate((inputs()[0]['bundle'], inputs()[5]['bundle'])):
                snapshot = codec.decode(codec.encode(source))
                actual = rpc.predict('pure-'+str(n), snapshot)
                assert codec.encode(actual['payload']) == codec.encode(old(snapshot))
            assert rpc.ledger[0]['cold_through_reply_ns'] >= rpc.ledger[0]['caller_elapsed_ns']
        assert rpc.closed and rpc.shutdown['process_exit_code'] == 0


def test_actual_both_zero_request_startups_record_complete_closure_and_proof(frozen_image,tmp_path):
    import os
    folder,version=frozen_image
    output=Path(os.environ['G31_JSON_FUNCTIONAL_OUTPUT'])
    loaded=[]
    for mode in ('reference','compiled'):
        with (tmp_path/(mode+'.stderr.log')).open('wb') as errors:
            with client.Client(folder,version,mode,timeout=30.,stderr=errors) as rpc:
                loaded.append(rpc.ready['loaded_sources'])
            record={'schema':'g31.json_prediction_startup_functional.v1','mode':mode,'version':version,
                'loaded_sources':rpc.ready['loaded_sources'],'proof':rpc.ready['proof'],
                'source_unchanged':rpc.shutdown['reply']['source_unchanged'],
                'closed_requests':rpc.shutdown['reply']['requests']}
        (output/f'startup_{mode}.json').write_bytes(codec.artifact_encode(record))
    assert loaded[0]==loaded[1]


def test_actual_replay_closes_owned_child(frozen_image, tmp_path):
    folder, version = frozen_image
    with (tmp_path/'stderr.log').open('wb') as errors:
        rpc = client.Client(folder, version, 'compiled', timeout=30., stderr=errors)
        rpc.predict('same', {})
        with pytest.raises(ValueError, match='EOF'):
            rpc.predict('same', {})
        assert rpc.closed and rpc.process.poll() is not None


def test_timeout_does_not_allow_next_request(frozen_image, tmp_path):
    folder, version = frozen_image
    with (tmp_path/'stderr.log').open('wb') as errors:
        rpc = client.Client(folder, version, 'compiled', timeout=30., stderr=errors)
        rpc.deadline = time.monotonic()-1
        with pytest.raises(TimeoutError): rpc.predict('timeout', {})
        assert rpc.closed and rpc.process.poll() is not None
        with pytest.raises(ValueError, match='closed'): rpc.predict('later', {})


def test_real_watchdog_closes_owned_child_while_waiting_for_input(frozen_image,tmp_path):
    import threading
    folder,version=frozen_image
    with (tmp_path/'stderr.log').open('wb') as errors:
        rpc=client.Client(folder,version,'compiled',timeout=30.,stderr=errors)
        rpc.watchdog.cancel()
        rpc.watchdog=threading.Timer(.05,rpc._expire)
        rpc.watchdog.start()
        try:
            rpc.process.wait(timeout=2.)
            # Windows Job close may yield exitcode0: timeout status, never the
            # exit code alone, determines whether any result is certified.
            assert rpc.expired.is_set() and rpc.process.poll() is not None
            with pytest.raises(TimeoutError): rpc._next()
            assert not hasattr(rpc,'shutdown')
        finally:rpc.abort()


def test_changed_image_during_lifetime_fails_shutdown(frozen_image, tmp_path):
    source, _ = frozen_image
    import shutil
    folder = tmp_path/'changed'; shutil.copytree(source, folder)
    version = codec.sha_bytes((folder/'manifest.json').read_bytes())
    with (tmp_path/'stderr.log').open('wb') as errors:
        rpc = client.Client(folder, version, 'compiled', timeout=30., stderr=errors)
        path = folder/'scripts/experiments/g31_ics_circulation/json_prediction_worker.py'
        path.write_bytes(path.read_bytes()+b'\n')
        with pytest.raises(ValueError, match='EOF'): rpc.close()
        assert rpc.closed and rpc.process.poll() is not None
