"""One caller, either the frozen compiled worker or two exact fixed halves.

Old RPC methods are inherited unchanged. Only the child entry filename in the
new subclass constructor is changed, proven by an exact AST restoration. A
failure in either half retires the complete logical request and both children.
"""
from __future__ import annotations
import ast
import copy
import inspect
import queue
import textwrap
import threading
import time
from . import json_prediction_client as original
from . import json_prediction_image as codec

OLD_ENTRY = 'scripts/experiments/g31_ics_circulation/json_prediction_worker.py'
NEW_ENTRY = 'scripts/experiments/g31_ics_circulation/json_prediction_shard_worker.py'


def constructor():
    tree = ast.parse(textwrap.dedent(inspect.getsource(original.Client.__init__)))
    before = ast.dump(tree, include_attributes=False)
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value == OLD_ENTRY]
    if len(matches) != 1:
        raise ValueError('unreviewed_client_entry_AST')
    matches[0].value = NEW_ENTRY
    restored = copy.deepcopy(tree)
    for node in ast.walk(restored):
        if isinstance(node, ast.Constant) and node.value == NEW_ENTRY:
            node.value = OLD_ENTRY
    if ast.dump(restored, include_attributes=False) != before:
        raise ValueError('client_constructor_changed')
    namespace = dict(original.Client.__init__.__globals__)
    exec(compile(ast.fix_missing_locations(tree), __file__+':entry_only', 'exec'), namespace)
    return namespace['__init__']


class ShardClient(original.Client):
    __init__ = constructor()


def merge(parts, snapshot):
    if type(parts) is not list or len(parts) != 2:
        raise ValueError('two_shards_required')
    expected_snapshot = codec.sha_bytes(codec.encode(snapshot))
    baseline, actions, predictions = None, None, []
    for index, part in enumerate(parts):
        if (type(part) is not dict or set(part) != {'baseline','actions','predictions','ordinals',
                'snapshot_sha256','action_domain_sha256','physical_baselines','candidate_queries'}
                or part['ordinals'] != list(range(index*16, (index+1)*16))
                or any(type(i) is not int for i in part['ordinals'])
                or type(part['physical_baselines']) is not int or part['physical_baselines'] != 1
                or type(part['candidate_queries']) is not int or part['candidate_queries'] != 16
                or len(part['actions']) != 32 or len(part['predictions']) != 16
                or part['snapshot_sha256'] != expected_snapshot
                or part['action_domain_sha256'] != codec.sha_bytes(codec.encode(part['actions']))):
            raise ValueError('shard_domain_or_snapshot_mismatch')
        if index == 0:
            baseline, actions = part['baseline'], part['actions']
        elif (codec.encode(part['baseline']) != codec.encode(baseline)
                or codec.encode(part['actions']) != codec.encode(actions)):
            raise ValueError('shard_baseline_or_order_mismatch')
        predictions.extend(part['predictions'])
    # Fresh return objects; no shard ledger/payload aliases escape through merge.
    return copy.deepcopy({'baseline':baseline, 'actions':actions, 'predictions':predictions})


class LogicalClient:
    def __init__(self, arm, images, *, timeout, stderrs, startup_attempts=None):
        if arm not in ('single', 'split') or len(stderrs) != (1 if arm == 'single' else 2):
            raise ValueError('fixed_logical_arm')
        if type(timeout) not in (int,float) or not 0 < timeout < float('inf'):
            raise ValueError('invalid_logical_lifetime_timeout')
        self.arm, self.started_ns = arm, time.perf_counter_ns()
        self.clients, self.ledger, self.closed, self.cleanup_errors = [], [], False, []
        self.startup_attempts = [] if startup_attempts is None else startup_attempts
        deadline = time.monotonic()+timeout
        try:
            specs = [('single','compiled',original.Client)] if arm == 'single' else [
                ('split','shard0',ShardClient), ('split','shard1',ShardClient)]
            for (image_key, mode, cls), stderr in zip(specs, stderrs, strict=True):
                image = images[image_key]
                attempt = {'mode':mode,'status':'unknown_starting','attempted_ns':time.perf_counter_ns()}
                self.startup_attempts.append(attempt)
                client = cls.__new__(cls)
                self.clients.append(client)
                try:
                    cls.__init__(client,image['path'],image['version'],mode,
                        timeout=max(.001,deadline-time.monotonic()),stderr=stderr)
                    attempt['status'] = 'ready'
                except BaseException as error:
                    attempt.update(status='unknown_failed',error=repr(error))
                    raise
                finally:
                    attempt.update(command=getattr(client,'command',None),
                        pid=getattr(getattr(client,'process',None),'pid',None),
                        returned_ns=time.perf_counter_ns())
            self.ready_ns = time.perf_counter_ns()
        except BaseException:
            self.abort()
            raise

    def predict(self, request_id, snapshot):
        start = time.perf_counter_ns()
        if self.closed:
            raise ValueError('logical_client_closed')
        # Common caller isolation/identity work is charged in both arms.
        threads, replies, errors = [], {}, []
        try:
            snapshot = codec.decode(codec.encode(snapshot))
            if self.arm == 'single':
                response = self.clients[0].predict(request_id+':0',snapshot)
                replies[0] = response
            else:
                messages = queue.Queue(maxsize=2)
                def call(index):
                    try:
                        response = self.clients[index].predict(request_id+':'+str(index),snapshot)
                        messages.put((index,response,None))
                    except BaseException as error:
                        messages.put((index,None,error))
                for index in range(2):
                    thread = threading.Thread(target=call,args=(index,),daemon=True)
                    threads.append(thread);thread.start()
                for _ in range(2):
                    index,response,error = messages.get()
                    if error is not None:
                        errors.append(repr(error))
                        self.abort()
                        raise RuntimeError('unknown_shard_failure:'+repr(error)) from error
                    if index in replies:
                        raise ValueError('duplicate_shard_reply')
                    replies[index] = response
            received = time.perf_counter_ns()
            payload = (copy.deepcopy(replies[0]['payload']) if self.arm == 'single' else
                merge([replies[i]['payload'] for i in range(2)],snapshot))
            # Identical whole-result caller codec and ledger cost, after merge.
            payload = codec.decode(codec.encode(payload))
            result = {'payload':payload,'native_authority':False,'complete_100ms_certified':False}
            row = {'request_id':request_id,'arm':self.arm,'caller_admitted_ns':start,
                'all_replies_ns':received,'snapshot':snapshot,
                'worker_samples':[copy.deepcopy(client.ledger[-1]) for client in self.clients],
                'merged_payload':copy.deepcopy(payload),
                'physical_baselines':len(self.clients),'candidate_queries':32,
                'sum_worker_compute_ns':sum(replies[i]['compute_wall_ns'] for i in replies)}
            self.ledger.append(row)
            row['caller_body_finished_ns'] = time.perf_counter_ns()
            row['caller_elapsed_ns'] = row['caller_body_finished_ns']-start
            return result
        except BaseException:
            self.abort()
            raise
        finally:
            for thread in threads:
                if thread.ident is not None:
                    thread.join()

    def close(self):
        start = time.perf_counter_ns()
        results = []
        try:
            for client in self.clients:
                results.append(client.close())
        finally:
            self.abort()
        if self.cleanup_errors:
            raise RuntimeError('owned_cleanup_errors:'+repr(self.cleanup_errors))
        self.shutdown = {'close_admitted_ns':start,'closed_and_reclaimed_ns':time.perf_counter_ns(),
            'workers':copy.deepcopy(results)}
        return self.shutdown

    def abort(self):
        self.closed = True
        errors = []
        for client in self.clients:
            try:
                client.abort()
            except BaseException as error:
                errors.append(repr(error))
        self.cleanup_errors.extend(errors)
        return errors
