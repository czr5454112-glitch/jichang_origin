"""Uninstalled, source-bound root-observation adapter; never a session proxy.

Only private function namespaces are used. The original background scheduler,
its .05 ticks and owner policy functions are unchanged. Native dispatch and a
complete experiment package have NOT been authorized by this module.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import json
import textwrap
import time

from . import initial_owner_route_campaign as original
from . import initial_owner_route_request as request
from .initial_owner_route_observation_gate import RootObservationGate

MUTATING_ADVANCES = frozenset(('advance_to', 'advance_until_owner_notification',
                              'step', 'result_at', 'restore', 'fork'))


def tree(function):
    return ast.parse(textwrap.dedent(inspect.getsource(function)))


def dump(node):return ast.dump(node, include_attributes=False)
def ordered(value):return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
def require(value, reason):
    if not value:raise ValueError('root_observation_adapter:' + reason)


def native_advance_sites(function):
    return [ast.unparse(n.func) for n in ast.walk(tree(function))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in MUTATING_ADVANCES]


def no_hidden_policy_advances(policies, client):
    """Closed selected method inventory, not a claim about arbitrary plugins.

Every method dispatched on the actual two OwnerPolicy instances and transport
is bound by its code identity. The selected methods may submit through their
ordinary transport; these are separately detected through actual client.calls.
Future experiment preparation must additionally pin its complete import closure.
    """
    inventory = {}
    for label, instance in [*policies.items(), ('transport', client)]:
        for cls in type(instance).__mro__:
            if cls is object:continue
            for name, function in vars(cls).items():
                if not inspect.isfunction(function):continue
                key = f'{label}:{cls.__module__}.{cls.__qualname__}.{name}'
                sites = native_advance_sites(function)
                require(not sites, 'hidden_policy_native_advance:' + key)
                inventory[key] = {'code': function.__code__, 'function': function,
                    'source_sha256': hashlib.sha256(inspect.getsource(function).encode()).hexdigest()}
    return inventory


def collection_inventory():
    """Explicit native-read chain invoked by the fixed policy, before/within it.

The original root.collect advances once before this adapter exists. It is not
treated as part of a continuous cursor chain: the first scheduler step always
falls back. The selected collector functions only read the exact session.
This inventory is a source proof for the pinned program, not a sandbox for
arbitrary callbacks or adversarial Python mutation.
    """
    from . import native_preexisting_initial_adapter as initial
    adapter = request.adapter
    functions = (adapter.collect_initial_ledger, adapter.collect_native,
        adapter.previous.collect_initial_ledger, initial.collect_native,
        request.fixed_B_first_action)
    result = {}
    for function in functions:
        require(not native_advance_sites(function), 'collector_hidden_advance')
        result[function.__module__ + '.' + function.__qualname__] = {
            'source_sha256':hashlib.sha256(inspect.getsource(function).encode()).hexdigest(),
            'native_advance_sites':[]}
    require(native_advance_sites(request.InitialOwnerRequest.collect) == ['self.session.advance_to'],
            'initial_collection_advance_inventory')
    require(not native_advance_sites(request.InitialOwnerRequest.observe_after_boundary),
            'observation_hidden_advance')
    require(not native_advance_sites(request.InitialOwnerRequest.final_revalidate_and_submit),
            'final_recheck_hidden_advance')
    return {'collectors':result, 'pre_chain_collection_advances':['self.session.advance_to'],
            'pre_chain_resets_continuity':True, 'runtime_callback_plugins_supported':False}


def admission_matches(rows, before, root_id, now):
    if type(before) is not int or before < 0 or len(rows) != before + 1:return False
    row = rows[-1]
    return (row.get('root_id') == f'activation:{before}:A' and row.get('owner') == 'A'
        and row.get('accepted_at') == now and row.get('scope') == 'owner_activation_proxy'
        and row.get('trigger') == {'kind':'initial_A_continuation','root_id':root_id})


def project_outbox(rows):
    """Complete identity inventory; only fields consumed by the pure gate.

Native ACK objects are not converted into new authority. This is a snapshot of
the genuine LocalTransport state whose immutable calls/ACK handling are retained.
    """
    if type(rows) is not dict:return None
    result = {}
    for identity, row in rows.items():
        if type(row) is not dict:
            result[identity] = row;continue
        payload = row.get('request')
        result[identity] = {key: row[key] for key in ('kind', 'terminal', 'next_retry') if key in row}
        result[identity]['request'] = ({key: payload[key] for key in ('request_id','owner_id') if key in payload}
                                      if type(payload) is dict else payload)
    return copy.deepcopy(result)


class _RecordedChain:
    """Data/call core also usable for recorded pure tests; no authority claim."""
    def __init__(self, session, client, root):
        self.session, self.client, self.root = session, client, root
        self.gate = RootObservationGate()
        self.calls = []
        self.last_notification = None
        self.step_start = None
        self.last_step_after_call = 0
        self.pending_proof = None
        self.schema = 'g31.initial_root.actual_advance_chain.v1'

    def invoke(self, method, args, kwargs, role):
        before = self.session.physical_time
        record = {'ordinal':len(self.calls), 'method':method, 'role':role,
                  'args':copy.deepcopy(args), 'kwargs':copy.deepcopy(kwargs),
                  'before':before, 'started_ns':time.perf_counter_ns()}
        try:
            result = getattr(self.session, method)(*args, **kwargs)
            record['response'] = copy.deepcopy(result)
            return result  # exact actual object, not an observation proxy
        except BaseException as error:
            record['error'] = repr(error)
            raise
        finally:
            record.update(after=self.session.physical_time, finished_ns=time.perf_counter_ns())
            self.calls.append(record)

    def notification_advance(self, owners, cursors, horizon, **kwargs):
        result = self.invoke('advance_until_owner_notification', (owners,cursors,horizon), kwargs, 'scheduler')
        self.last_notification = len(self.calls)-1
        return result

    def root_drain(self, now, **kwargs):
        return self.invoke('advance_to', (now,), kwargs, 'root_same_timestamp_drain')

    def final_drain(self, horizon, **kwargs):
        return self.invoke('advance_to', (horizon,), kwargs, 'scheduler_final_drain')

    def decide(self, response):
        index = self.last_notification
        valid = (index is not None and index==len(self.calls)-1
            and index==self.last_step_after_call and 'error' not in self.calls[index])
        record = self.calls[index] if index is not None else None
        valid = valid and (record['args'][0]==['A','B']
            and record['after']==self.session.physical_time
            and ordered(record['response'])==ordered(response))
        self.step_start = len(self.root.events)
        if record is None:
            inputs = dict(before=self.session.physical_time,horizon=self.session.physical_time,
                response=response,cursor_before=None,now=self.session.physical_time,
                protocol_call_count=len(self.client.calls),outbox=project_outbox(self.client.rows),
                root_state=self.root.state,all_native_advances_observed=False)
        else:
            inputs = dict(before=record['before'],horizon=record['args'][2],
                response=response,cursor_before=record['args'][1],now=self.session.physical_time,
                protocol_call_count=len(self.client.calls),outbox=project_outbox(self.client.rows),
                root_state=self.root.state,all_native_advances_observed=bool(valid))
        proof = self.gate.decide(**inputs)
        self.pending_proof = {'inputs':copy.deepcopy(inputs),'decision':copy.deepcopy(proof),
                              'notification_call':copy.deepcopy(record)}
        # This record's boolean was computed from this actual call sequence.
        # It is never taken from external JSON as runtime permission.
        self.root._record('root_observation_gate', self.pending_proof)
        return proof['skip']

    def after_step(self, skipped, admission_before):
        events = self.root.events[self.step_start:]
        expected_admissions = admission_matches(self.client.roots,admission_before,
                                               self.root.request_id,self.session.physical_time)
        full = False
        drain = None
        if not skipped and len(self.calls)>self.last_notification+1:
            drain = self.calls[-1]
            tail = [e for e in events if e['stage'] in ('mandatory_drain','post_drain_observation')]
            full = (len(self.calls)==self.last_notification+2
                and drain['role']=='root_same_timestamp_drain' and 'error' not in drain
                and drain['before']==drain['after']==self.session.physical_time
                and len(tail)==2 and [e['stage'] for e in tail]==['mandatory_drain','post_drain_observation']
                and ordered(tail[0]['value'])==ordered(drain['response'])
                and request.native_boundary_complete(drain['response'],self.session.physical_time)
                and tail[1]['value']['view']['now']==self.session.physical_time)
        if skipped:
            expected_admissions = expected_admissions and len(self.calls)==self.last_notification+1
        outcome = self.gate.after_step(now=self.session.physical_time,
            protocol_call_count=len(self.client.calls),original_admission_retained=expected_admissions,
            full_root_observation_and_drain_completed=full)
        self.last_step_after_call = len(self.calls)
        self.root._record('root_observation_gate_completion',{
            'skipped':skipped,'completion':outcome,'actual_drain_call':copy.deepcopy(drain),
            'admissions_before':admission_before,'admissions_after':len(self.client.roots),
            'admission':copy.deepcopy(self.client.roots[-1]) if self.client.roots else None,
            'protocol_call_count_after':len(self.client.calls)})

    def audit_copy(self):
        """Caller must include this copy/encoding cost in its declared envelope."""
        return {'schema':self.schema,'calls':copy.deepcopy(self.calls),
                'runtime_authority_from_saved_json':False}


class ActualAdvanceChain(_RecordedChain):
    def __init__(self, session, client, root, policies):
        require(session is root.session and client is root.client, 'foreign_session_or_client')
        require(request.adapter._valid_handle(root.native,session,root.accepted), 'missing_actual_accepted_session')
        require(root.drain_and_finish_if_closed.__func__ is TRACKED_ROOT_DRAIN, 'untracked_root_drain')
        require(root.observe_after_boundary.__func__ is request.InitialOwnerRequest.observe_after_boundary,
                'unknown_root_observer')
        require(root._record.__func__ is request.InitialOwnerRequest._record,'unknown_root_recorder')
        require(not hasattr(root, '_observation_advance_chain'), 'single_use_chain')
        require(type(client) is original.public.LocalTransport,'unknown_transport_class')
        require(not policies or (set(policies)=={'A','B'} and all(
            type(p) is request.FixedContinuationOwner and p.session is session and p.client is client
            and p.owner==owner for owner,p in policies.items())), 'unknown_policy_instances')
        self.method_inventory = no_hidden_policy_advances(policies, client)
        self.collection_source_inventory = collection_inventory()
        super().__init__(session,client,root)
        root._observation_advance_chain = self


def _actual_root_drain(root, now, **kwargs):
    chain = getattr(root,'_observation_advance_chain',None)
    require(type(chain) is ActualAdvanceChain and chain.root is root, 'missing_actual_root_chain')
    return chain.root_drain(now,**kwargs)


def _compile_root_drain():
    source = request.InitialOwnerRequest.drain_and_finish_if_closed
    syntax=tree(source);original_tree=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='self.session.advance_to':
            node.func=ast.Name(id='_actual_root_drain',ctx=ast.Load())
            node.args.insert(0,ast.Name(id='self',ctx=ast.Load()));count+=1
    require(count==1 and native_advance_sites(source)==['self.session.advance_to'],'root_drain_source_shape')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='_actual_root_drain':
            node.func=ast.parse('self.session.advance_to',mode='eval').body;node.args.pop(0)
    require(dump(restored)==dump(original_tree),'root_drain_ast_not_exact')
    namespace={**source.__globals__,'_actual_root_drain':_actual_root_drain}
    exec(compile(ast.fix_missing_locations(syntax),'<tracked-original-root-drain>','exec'),namespace)
    return namespace[source.__name__]


TRACKED_ROOT_DRAIN=_compile_root_drain()


def request_type(original_type):
    """New class only; the original type and all its method objects stay intact."""
    require(issubclass(original_type,request.InitialOwnerRequest),'unknown_request_base')
    return type('Gated'+original_type.__name__,(original_type,),
                {'drain_and_finish_if_closed':TRACKED_ROOT_DRAIN})


def continuation(function):
    """Compile exact selected scheduler AST with only explicit local hooks."""
    require(function.__code__ is original.run_continuation.__code__, 'unknown_scheduler_code')
    syntax=tree(function);original_tree=copy.deepcopy(syntax)
    fn=syntax.body[0];count_notification=count_final=0
    for node in ast.walk(syntax):
        if not isinstance(node,ast.Call):continue
        if ast.unparse(node.func)=='session.advance_until_owner_notification':
            node.func=ast.parse('_chain.notification_advance',mode='eval').body;count_notification+=1
        elif ast.unparse(node.func)=='session.advance_to':
            node.func=ast.parse('_chain.final_drain',mode='eval').body;count_final+=1
    require(count_notification==count_final==1,'scheduler_advance_inventory')
    loop=next(node for node in fn.body if isinstance(node,ast.While))
    target=next(node for node in loop.body if isinstance(node,ast.If)
                and ast.unparse(node.test)=="root.state == 'pending_first_hop_and_ack'")
    expected=ast.parse("""if root.state == 'pending_first_hop_and_ack':
    root.observe_after_boundary(response)
    verdict = root.drain_and_finish_if_closed()
    if verdict['closed']:
        publish_root(root, root_records)
""").body[0]
    require(dump(target)==dump(expected),'scheduler_root_block_changed')
    observer_body=tree(request.InitialOwnerRequest.observe_after_boundary).body[0].body
    boundary=next(node for node in observer_body if isinstance(node,ast.Assign)
        and ast.unparse(node.targets[0])=='self.last_boundary')
    admission=next(node for node in observer_body
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
        and ast.unparse(node.value.func)=='self.client.activate')
    class Rename(ast.NodeTransformer):
        def visit_Name(self,node):
            return ast.copy_location(ast.Name(id='root',ctx=node.ctx),node) if node.id=='self' else node
    admission=Rename().visit(copy.deepcopy(admission))
    boundary=Rename().visit(copy.deepcopy(boundary))
    # now in the extracted expression is the unchanged scheduler's actual now.
    skipbranch=ast.If(test=ast.Name(id='_skip',ctx=ast.Load()),body=[boundary,admission],orelse=copy.deepcopy(expected.body[:2]))
    target.body=ast.parse('_admissions_before = len(client.roots)\n_skip = _chain.decide(response)').body+[skipbranch]+ast.parse(
        "_chain.after_step(_skip, _admissions_before)\nif not _skip and verdict['closed']:\n    publish_root(root, root_records)").body
    fn.body.insert(1,ast.parse('_chain = ActualAdvanceChain(session, client, root, policies)').body[0])
    # Independently undo exactly our additions; no background statement, tick,
    # activation location, cursor update or terminal handler may drift.
    restored=copy.deepcopy(syntax)
    rfn=restored.body[0]
    del rfn.body[1]
    rloop=next(node for node in rfn.body if isinstance(node,ast.While))
    rtarget=next(node for node in rloop.body if isinstance(node,ast.If)
                and ast.unparse(node.test)=="root.state == 'pending_first_hop_and_ack'")
    rtarget.body=copy.deepcopy(expected.body)
    for node in ast.walk(restored):
        if isinstance(node,ast.Call):
            if ast.unparse(node.func)=='_chain.notification_advance':
                node.func=ast.parse('session.advance_until_owner_notification',mode='eval').body
            elif ast.unparse(node.func)=='_chain.final_drain':
                node.func=ast.parse('session.advance_to',mode='eval').body
    require(dump(restored)==dump(original_tree),'scheduler_ast_not_exact')
    namespace={**function.__globals__,'ActualAdvanceChain':ActualAdvanceChain}
    exec(compile(ast.fix_missing_locations(syntax),'<gated-original-continuation>','exec'),namespace)
    result=namespace[function.__name__]
    result._source_proof={'scheduler_advance_sites':native_advance_sites(function),
        'root_drain_sites':native_advance_sites(request.InitialOwnerRequest.drain_and_finish_if_closed),
        'admission_ast':dump(admission),'original_root_block_ast':dump(expected),
        'actual_boundary_assignment_ast':dump(boundary),
        'exact_full_ast_restoration':True,
        'original_scheduler_ast_sha256':hashlib.sha256(dump(original_tree).encode()).hexdigest(),
        'background_tick_policy_or_activations_modified':False,
        'runtime_dispatch_ready':False}
    return result
