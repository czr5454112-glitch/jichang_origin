"""Explicit four-frame SAME-ACTION model continuation, not native state.

The old projections remain unchanged. This candidate lowers only control flow;
all event handlers and decision statements are compiled from source-bound AST
slices with their full defining globals. Arbitrary Python program counters,
actual observations, action changes and consumed continuations are unsupported.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import heapq
import inspect
from pathlib import Path
import textwrap
from types import CodeType

from . import public_live_obligation_lazy_communication_projection as lazy

VERSION = 'g31.live_obligation.conditional_continuation.v1'
PC = 'after_collect_before_record_and_action'
ORIGINAL_SHA = '0c77f130e31f2727d0f6b7f6e6425ae073e3bf5b97515843cf1d03cced5c56ea'
LAZY_SHA = '980f245dc3b3563968015a626ed5e127fd94efb70044eb24b67d9d948835f86f'


def require(value, reason):
    if not value: raise ValueError('conditional_continuation:' + reason)


def dump(node): return ast.dump(node, include_attributes=False)
def statements(text): return ast.parse(text).body
def expression(text): return ast.parse(text, mode='eval').body


def code_shape(code):
    """Include executable constants recursively; exclude only file/line tables."""
    return (code.co_code, tuple(code_shape(v) if isinstance(v, CodeType) else v for v in code.co_consts),
            code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
            code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
            code.co_flags, code.co_nlocals, code.co_exceptiontable)


def compile_body(name, arguments, body, defining_globals):
    function = ast.FunctionDef(name=name,
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=a) for a in arguments],
                           kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=copy.deepcopy(body), decorator_list=[])
    tree = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = dict(defining_globals)
    exec(compile(tree, '<conditional_continuation:'+name+'>', 'exec'), namespace)
    return namespace[name]


def tree_of(function): return ast.parse(textwrap.dedent(inspect.getsource(function)))


def lazy_activate_tree():
    # Reproduce the accepted source transform, then compare executable code.
    original = lazy.original.Projection.activate
    tree = tree_of(original); body = tree.body[0].body
    positions = [i for i, n in enumerate(body) if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'view']
    require(len(positions) == 1, 'lazy_unique_view')
    assignment = body.pop(positions[0]); require(ast.unparse(assignment.value) == 'self.world.view(owner)', 'lazy_view')
    class Replace(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == 'view': return ast.copy_location(copy.deepcopy(assignment.value), node)
            return node
    tree = ast.fix_missing_locations(Replace().visit(tree))
    namespace = dict(original.__globals__)
    exec(compile(tree, '<conditional_lazy_owner_view>', 'exec'), namespace)
    require(code_shape(namespace['activate'].__code__) == code_shape(lazy.Projection.activate.__code__),
            'accepted_lazy_code_shape')
    return tree


def generated_run_tree():
    original = lazy.original.physics.previous.original.Projection.run
    tree = tree_of(original); function = tree.body[0]
    loops = [n for n in function.body if isinstance(n, ast.While)]
    require(len(loops) == 1, 'one_run_loop'); loop = loops[0]
    positions = [i for i, n in enumerate(loop.body) if isinstance(n, ast.If) and ast.unparse(n.test) == "kind == 'tick'"]
    require(len(positions) == 1, 'unique_physical_handler'); i = positions[0]
    physical = loop.body[i]
    loop.body[i:i+1] = [statements('self.before_event(kind,args)')[0],
        ast.If(test=expression('self.protocol_event(kind,args)'), body=[ast.Pass()], orelse=[physical]),
        statements('self.after_event(kind,args)')[0]]
    final = function.body[-1]; require(isinstance(final, ast.Return), 'final_return')
    final.value = ast.Call(func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()),
                                            attr='finish', ctx=ast.Load()), args=[final.value], keywords=[])
    ast.fix_missing_locations(tree); namespace = dict(original.__globals__)
    exec(compile(tree, '<conditional_communication_physical_loop>', 'exec'), namespace)
    require(code_shape(namespace['run'].__code__) == code_shape(lazy.Projection.run.__code__),
            'accepted_generated_run_code_shape')
    return tree, original.__globals__


def build_parts():
    require(hashlib.sha256(Path(lazy.__file__).read_bytes()).hexdigest() == LAZY_SHA, 'lazy_source')
    require(hashlib.sha256(Path(lazy.original.__file__).read_bytes()).hexdigest() == ORIGINAL_SHA, 'original_source')
    lazy.original.physics.check_sources()
    decision = tree_of(lazy.original.Projection.decide); body = decision.body[0].body
    collect = statements('info,screen,view=self.collect(owner,p)')[0]
    indices = [i for i, n in enumerate(body) if dump(n) == dump(collect)]
    require(len(indices) == 1, 'unique_collection'); split = indices[0]+1
    d_prefix, d_tail = body[:split], body[split:]
    reconstructed = copy.deepcopy(decision); reconstructed.body[0].body = copy.deepcopy(d_prefix+d_tail)
    require(dump(reconstructed) == dump(decision), 'decide_inverse_AST')
    dg = lazy.original.Projection.decide.__globals__
    decide_prefix = compile_body('_decide_prefix', ['self', 'owner'],
        d_prefix+statements('return (s,p,info,screen,view)'), dg)
    decide_tail = compile_body('_decide_tail', ['self', 'owner', 's', 'p', 'info', 'screen', 'view'], d_tail, dg)

    activation = lazy_activate_tree(); body = activation.body[0].body
    call = statements('self.decide(owner)')[0]
    indices = [i for i, n in enumerate(body) if dump(n) == dump(call)]
    require(len(indices) == 1, 'unique_decide_call'); split = indices[0]
    a_prefix, a_tail = body[:split], body[split+1:]
    restored = copy.deepcopy(activation); restored.body[0].body = copy.deepcopy(a_prefix+[call]+a_tail)
    require(dump(restored) == dump(activation), 'activate_inverse_AST')
    ag = lazy.Projection.activate.__globals__
    activate_prefix = compile_body('_activate_prefix', ['self', 'owner'], a_prefix+statements('return (s,)'), ag)
    activate_tail = compile_body('_activate_tail', ['self', 'owner', 's'], a_tail, ag)

    tick = tree_of(lazy.original.Projection.tick)
    require(len(tick.body[0].body) == 1 and isinstance(tick.body[0].body[0], ast.For), 'tick_single_loop')
    owner_loop = tick.body[0].body[0]
    require(ast.unparse(owner_loop.target) == 'o' and not owner_loop.orelse and
            dump(ast.Module(body=owner_loop.body, type_ignores=[])) == dump(ast.parse('self.activate(o)')),
            'tick_body')
    owners = compile_body('_owners', ['self', 'owner'], [ast.Return(value=owner_loop.iter)],
                          lazy.original.Projection.tick.__globals__)

    run, rg = generated_run_tree(); body = run.body[0].body
    loop_index = next(i for i, n in enumerate(body) if isinstance(n, ast.While))
    loop = body[loop_index]; require(ast.unparse(loop.test) == 'self.events' and not loop.orelse, 'run_loop_shape')
    require(len(loop.body) == 7, 'run_loop_statement_count')
    header = ast.parse('''self.time, _, _, kind, args = heapq.heappop(self.events)
if self.time > legacy.HORIZON:
    break
count += 1
if count > 20000:
    return {'status': 'unknown_event_budget', 'completion': self.completed}
''').body
    require([dump(n) for n in loop.body[:4]] == [dump(n) for n in header], 'exact_pop_horizon_budget_header')
    require(dump(loop.body[4]) == dump(statements('self.before_event(kind,args)')[0]) and
            dump(loop.body[6]) == dump(statements('self.after_event(kind,args)')[0]), 'before_after_order')
    wrapper = loop.body[5]
    require(isinstance(wrapper, ast.If) and ast.unparse(wrapper.test) == 'self.protocol_event(kind, args)' and
            len(wrapper.body) == 1 and isinstance(wrapper.body[0], ast.Pass) and len(wrapper.orelse) == 1,
            'protocol_handler_wrapper')
    handler = wrapper.orelse[0]
    require(isinstance(handler, ast.If) and ast.unparse(handler.test) == "kind == 'tick'" and
            [dump(n) for n in handler.body] == [dump(statements('self.tick()')[0])], 'tick_handler')
    owner_handler = handler.orelse[0]
    require(isinstance(owner_handler, ast.If) and ast.unparse(owner_handler.test) == "kind == 'owner_activation'" and
            len(owner_handler.body) == 2 and dump(owner_handler.body[-1]) == dump(statements('self.tick(args[0])')[0]),
            'owner_handler')
    owner_start = compile_body('_owner_start', ['self', 'kind', 'args'], [
        ast.If(test=copy.deepcopy(owner_handler.test), body=copy.deepcopy(owner_handler.body[:1])+statements('return args[0]'), orelse=[]),
        ast.Return(value=ast.Constant(value=None))], rg)
    initialize = compile_body('_initialize', ['self'], body[:loop_index]+statements('return count'), rg)
    final = compile_body('_final', ['self', 'count'], body[loop_index+1:], rg)
    budget = compile_body('_budget', ['self'], [copy.deepcopy(header[-1].body[0])], rg)
    physical = compile_body('_physical', ['self', 'kind', 'args'], [handler], rg)
    # The full loop body was decomposed without omitting any statement.
    rebuilt = copy.deepcopy(run)
    rebuilt.body[0].body = copy.deepcopy(body[:loop_index])+[
        ast.While(test=copy.deepcopy(loop.test), body=copy.deepcopy(header)+copy.deepcopy(loop.body[4:]), orelse=[])]+copy.deepcopy(body[loop_index+1:])
    require(dump(rebuilt) == dump(run), 'run_inverse_AST')
    return dict(initialize=initialize, final=final, budget=budget, physical=physical,
        owner_start=owner_start, owners=owners, activate_prefix=activate_prefix, activate_tail=activate_tail,
        decide_prefix=decide_prefix, decide_tail=decide_tail), {
        'original_source_sha256': ORIGINAL_SHA, 'lazy_source_sha256': LAZY_SHA,
        'decide_inverse_AST': True, 'activate_inverse_AST': True, 'run_inverse_AST': True,
        'accepted_lazy_code_shape': True, 'accepted_generated_run_code_shape': True,
        'complete_defining_globals': True, 'physical_handler_statements_changed': False,
        'same_action_only': True, 'arbitrary_program_counters_supported': False}


PARTS, PROOF = build_parts()


class Projection(lazy.Projection):
    """The physical object retains all original methods and no extra actions."""


def build_engine():
    original = lazy.original.predict; tree = tree_of(original)
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and ast.unparse(n.value) == 'engine.run()']
    require(len(matches) == 1, 'predict_engine_return')
    before = copy.deepcopy(tree); matches[0].value = ast.Name(id='engine', ctx=ast.Load())
    inverse = copy.deepcopy(tree)
    node = next(n for n in ast.walk(inverse) if isinstance(n, ast.Return) and ast.unparse(n.value) == 'engine')
    node.value = expression('engine.run()'); require(dump(inverse) == dump(before), 'build_engine_inverse_AST')
    namespace = {**original.__globals__, 'Projection': Projection}
    exec(compile(ast.fix_missing_locations(tree), '<conditional_initial_engine>', 'exec'), namespace)
    return namespace['predict']


_build_engine = build_engine()


class Continuation:
    """Pure model control state. Not a serialized/native authority capability."""
    def __init__(self, engine, frames, action_bytes):
        self._engine, self._frames, self._action_bytes = engine, frames, action_bytes
        self._consumed = False

    def description(self):
        return {'schema': VERSION, 'program_counter': self._frames['pc'], 'consumed': self._consumed,
            'model_time': self._engine.time, 'event_count': self._frames['run']['count'],
            'native_authority': False, 'model_history_coverage_certified': False, 'same_action_only': True}


def validate(state, *, pc=None):
    require(type(state) is Continuation and not state._consumed, 'invalid_or_consumed_continuation')
    require(type(state._engine) is Projection, 'model_engine_type')
    require(lazy.original.context.encoded(state._engine.action) == state._action_bytes, 'changed_action')
    frames = state._frames
    require(type(frames) is dict and frames['pc'] in ('next_event', PC), 'unsupported_program_counter')
    if pc is not None: require(frames['pc'] == pc, 'wrong_entry_program_counter')
    run = frames['run']
    require(run['initialized'] is True and type(run['count']) is int and 0 <= run['count'] <= 20000,
            'run_frame')
    if frames['pc'] == PC:
        tick, activation, decision = frames['tick'], frames['activate'], frames['decide']
        require(run['event'] is not None and run['event'][3] in ('tick', 'owner_activation') and
                run['handler_pc'] == 'owner_handler' and tick is not None and activation is not None and decision is not None,
                'active_frames')
        owner = tick['owners'][tick['index']]
        require(owner == activation['owner'] == decision['owner'] and
                activation['s'] is decision['s'] is state._engine.owner_state[owner] and
                decision['p'] is decision['s']['pending'], 'active_frame_aliases')


def start_conditional(supplied_initial_context, fixed_action):
    engine = _build_engine(supplied_initial_context, fixed_action)
    if type(engine) is not Projection: return engine
    try:
        count = PARTS['initialize'](engine)
        require(type(count) is int and count == 0, 'initial_count')
        frames = {'pc': 'next_event', 'run': {'initialized': True, 'count': count,
            'event': None, 'handler_pc': 'next_event'}, 'tick': None, 'activate': None, 'decide': None}
        return Continuation(engine, frames, lazy.original.context.encoded(engine.action))
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        return lazy.original.context.unknown('conditional_projection:' + str(exc))


def fork_conditional(state):
    validate(state)
    engine, frames = copy.deepcopy((state._engine, state._frames))
    result = Continuation(engine, frames, state._action_bytes); validate(result)
    return result


def _complete_activation(engine, frames):
    activation = frames['activate']
    PARTS['activate_tail'](engine, activation['owner'], activation['s'])
    frames['activate'] = None; frames['tick']['index'] += 1


def _continue_tick(engine, frames):
    tick = frames['tick']
    while tick['index'] < len(tick['owners']):
        owner = tick['owners'][tick['index']]
        activated = PARTS['activate_prefix'](engine, owner)
        if activated is None:
            tick['index'] += 1; continue
        (s,) = activated
        frames['activate'] = {'owner': owner, 's': s}
        decision = PARTS['decide_prefix'](engine, owner)
        if decision is not None:
            ds, p, info, screen, view = decision
            require(ds is s and p is s['pending'], 'collected_frame_aliases')
            frames['decide'] = {'owner': owner, 's': s, 'p': p, 'info': info, 'screen': screen, 'view': view}
            frames['pc'] = PC
            return False
        _complete_activation(engine, frames)
    frames['tick'] = None
    return True


def _after_owner_handler(engine, frames):
    event = frames['run']['event']
    engine.after_event(event[3], event[4])
    frames['run']['event'] = None; frames['run']['handler_pc'] = 'next_event'; frames['pc'] = 'next_event'


def _drive(state, *, resume):
    validate(state, pc=PC if resume else 'next_event')
    state._consumed = True
    engine, frames, identity = state._engine, state._frames, state._action_bytes
    try:
        if resume:
            decision = frames['decide']
            PARTS['decide_tail'](engine, decision['owner'], decision['s'], decision['p'],
                                decision['info'], decision['screen'], decision['view'])
            frames['decide'] = None
            _complete_activation(engine, frames)
            if not _continue_tick(engine, frames): return Continuation(engine, frames, identity)
            _after_owner_handler(engine, frames)
        while engine.events:
            event = heapq.heappop(engine.events)
            engine.time, _, _, kind, args = event
            frames['run']['event'] = event
            if engine.time > lazy.original.physics.previous.original.legacy.HORIZON:
                frames['run']['handler_pc'] = 'horizon_popped_before_count'
                return PARTS['final'](engine, frames['run']['count'])
            frames['run']['count'] += 1
            if frames['run']['count'] > 20000:
                frames['run']['handler_pc'] = 'event_budget_before_hooks'
                return PARTS['budget'](engine)
            engine.before_event(kind, args)
            handled = engine.protocol_event(kind, args)
            if not handled:
                if kind in ('tick', 'owner_activation'):
                    owner = PARTS['owner_start'](engine, kind, args)
                    frames['run']['handler_pc'] = 'owner_handler'
                    frames['tick'] = {'owners': PARTS['owners'](engine, owner), 'index': 0}
                    if not _continue_tick(engine, frames): return Continuation(engine, frames, identity)
                else:
                    PARTS['physical'](engine, kind, args)
            engine.after_event(kind, args)
            frames['run']['event'] = None; frames['run']['handler_pc'] = 'next_event'
        return PARTS['final'](engine, frames['run']['count'])
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        return lazy.original.context.unknown('conditional_projection:' + str(exc))


def advance_to_collection_or_terminal(state):
    return _drive(state, resume=False)


def resume_same_action(state):
    return _drive(state, resume=True)


def source_proof(): return copy.deepcopy(PROOF)
