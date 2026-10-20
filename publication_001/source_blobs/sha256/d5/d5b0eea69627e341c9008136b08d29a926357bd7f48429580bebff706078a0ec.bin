"""Private C-digest routing for the existing complete saved bridge audit.

No extension is loaded here and no driver is installed. The explicit caller
must perform the accepted C authority and full entry/exit checks. Synthetic
tests use _bundle only to prove routing; they do not establish C byte parity.
"""
from __future__ import annotations

from types import FunctionType, SimpleNamespace

from . import bridge_saved_text_actor as previous
from . import cooperative_bridge_policy as policy
from . import current_empty_possession_permit as possession
from . import planning_capture_v2_c_encoder as encoder
from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse

frozen = previous.frozen
r = frozen.r
full = frozen.full
require = frozen.require
C32_REVIEW = 'dpc_prepare_001/root_saved_review_001.json'
C32_REVIEW_SHA = '93690fcb1bb4fdf48463f5451d4d435225c0f4e28b3990797ac988ab1abe38f1'

_FUNCTIONS = (
    base.delivered_peer, base.Owner.activate, reuse.latest_own_capture,
    possession.PossessionGate.consume, policy.BridgeOwner.__init__,
    policy.BridgeOwner.activate, policy.run_policy, policy.cap_relay_evidence,
    r.runner_namespace, r.original.assess, r.original.isolated_base,
    full.verify_case,
)
_IDENTITIES = tuple((fn, fn.__code__, fn.__defaults__, fn.__kwdefaults__,
                     fn.__closure__, dict(fn.__globals__)) for fn in _FUNCTIONS)
_CLASSES = (base.Owner, policy.BridgeOwner, possession.PossessionGate)


def clone(function, namespace):
    """The defining function's complete globals, defaults and cells survive."""
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    value.__annotations__ = dict(function.__annotations__)
    value.__qualname__ = function.__qualname__
    value.__doc__ = function.__doc__
    return value


def original_identity():
    require((base.Owner, policy.BridgeOwner, possession.PossessionGate) == _CLASSES,
            'C_digest_original_classes')
    for fn, code, defaults, kwdefaults, closure, namespace in _IDENTITIES:
        require(fn.__code__ is code and fn.__defaults__ is defaults
            and fn.__kwdefaults__ is kwdefaults and fn.__closure__ is closure
            and set(fn.__globals__) == set(namespace)
            and all(fn.__globals__[k] is v for k, v in namespace.items()),
            'C_digest_original_function_or_globals')
    require(base.delivered_peer is _FUNCTIONS[0] and base.Owner.activate is _FUNCTIONS[1]
        and reuse.latest_own_capture is _FUNCTIONS[2]
        and possession.PossessionGate.consume is _FUNCTIONS[3]
        and policy.BridgeOwner.__init__ is _FUNCTIONS[4]
        and policy.BridgeOwner.activate is _FUNCTIONS[5]
        and policy.run_policy is _FUNCTIONS[6] and policy.cap_relay_evidence is _FUNCTIONS[7]
        and r.runner_namespace is _FUNCTIONS[8] and r.original.assess is _FUNCTIONS[9]
        and r.original.isolated_base is _FUNCTIONS[10] and full.verify_case is _FUNCTIONS[11],
        'C_digest_original_member')


def clone_proof(original, replacement, changes):
    require(replacement.__code__ is original.__code__
        and replacement.__defaults__ is original.__defaults__
        and replacement.__kwdefaults__ is original.__kwdefaults__
        and replacement.__closure__ is original.__closure__, 'C_digest_clone_identity')
    expected = {**original.__globals__, **changes}
    require(set(replacement.__globals__) == set(expected)
        and all(replacement.__globals__[k] is value for k, value in expected.items()),
        'C_digest_clone_full_globals')
    return {'function': original.__module__ + '.' + original.__qualname__,
        'original_code_defaults_kwdefaults_cells': True,
        'full_global_domain_preserved': True, 'replaced_globals': sorted(changes)}


def facade_proof(original, replacement, changes):
    expected = {**vars(original), **changes}
    require(set(vars(replacement)) == set(expected)
        and all(vars(replacement)[k] is value for k, value in expected.items()),
        'C_digest_facade_full_domain')


def _bundle(digest):
    """Private synthetic seam. Only bind() accepts an actual encoder Candidate.

    This function creates no acceptance or build authority from a callable.
    Each invocation owns fresh classes, facades and globals dictionaries.
    """
    original_identity()
    require(callable(digest), 'C_digest_callable')
    checks = []

    def changed(function, **updates):
        result = clone(function, {**function.__globals__, **updates})
        checks.append((function, result, updates))
        return result

    validator = changed(base.delivered_peer, capture_digest_v2=digest)
    base_facade = SimpleNamespace(**{**vars(base), 'delivered_peer': validator})
    base_activate = changed(base.Owner.activate, delivered_peer=validator)
    PrivateBaseOwner = type('PrivateDigestBaseOwner', (base.Owner,), {'activate': base_activate})
    base_facade.Owner = PrivateBaseOwner

    own_capture = changed(reuse.latest_own_capture, base=base_facade)
    reuse_facade = SimpleNamespace(**{**vars(reuse), 'latest_own_capture': own_capture})
    consume = changed(possession.PossessionGate.consume, base=base_facade, reuse=reuse_facade)
    PrivateGate = type('PrivateDigestPossessionGate', (possession.PossessionGate,), {'consume': consume})

    initialize = changed(policy.BridgeOwner.__init__, PossessionGate=PrivateGate)
    activate = changed(policy.BridgeOwner.activate, base=base_facade,
                       reuse=reuse_facade, PossessionGate=PrivateGate)
    PrivateBridgeOwner = type('PrivateDigestBridgeOwner', (policy.BridgeOwner, PrivateBaseOwner),
                             {'__init__': initialize, 'activate': activate})
    relay = changed(policy.cap_relay_evidence, base=base_facade)
    run_policy = changed(policy.run_policy, BridgeOwner=PrivateBridgeOwner)
    policy_facade = SimpleNamespace(**{**vars(policy), 'BridgeOwner': PrivateBridgeOwner,
                                      'run_policy': run_policy, 'cap_relay_evidence': relay})

    def runner_namespace():
        # This is the original factory's fresh dictionary. Its inherited
        # functions already close over this exact dict. Never replace vars of
        # the original module with a facade and break its identity filter.
        namespace = r.runner_namespace()
        namespace['policy'] = policy_facade
        require(namespace['assess'].__globals__ is namespace
            and namespace['isolated_base'].__globals__ is namespace,
            'C_digest_runner_shared_fresh_globals')
        require(namespace['assess'].__code__ is r.original.assess.__code__
            and namespace['isolated_base'].__code__ is r.original.isolated_base.__code__,
            'C_digest_runner_function_code')
        return namespace

    runner_facade = SimpleNamespace(**{**vars(r), 'runner_namespace': runner_namespace})
    checker = changed(full.verify_case, policy=policy_facade)
    full_facade = SimpleNamespace(**{**vars(full), 'verify_case': checker})

    def prove():
        original_identity()
        proofs = [clone_proof(*item) for item in checks]
        for original, replacement, changes in (
            (base, base_facade, {'delivered_peer': validator, 'Owner': PrivateBaseOwner}),
            (reuse, reuse_facade, {'latest_own_capture': own_capture}),
            (policy, policy_facade, {'BridgeOwner': PrivateBridgeOwner,
                                    'run_policy': run_policy, 'cap_relay_evidence': relay}),
            (r, runner_facade, {'runner_namespace': runner_namespace}),
            (full, full_facade, {'verify_case': checker}),
        ):
            facade_proof(original, replacement, changes)
        require(PrivateBridgeOwner.__mro__ == (PrivateBridgeOwner, policy.BridgeOwner,
            PrivateBaseOwner, base.Owner, object), 'C_digest_super_MRO')
        dummy = PrivateBridgeOwner.__new__(PrivateBridgeOwner)
        require(super(policy.BridgeOwner, dummy).activate.__func__ is base_activate
            and super(policy.BridgeOwner, dummy).__init__.__func__ is base.Owner.__init__,
            'C_digest_actual_super_targets')
        require(PrivateGate.__mro__ == (PrivateGate, possession.PossessionGate, object)
            and PrivateBaseOwner.__mro__ == (PrivateBaseOwner, base.Owner, object)
            and PrivateBaseOwner.activate is base_activate
            and PrivateGate.consume is consume and PrivateGate.__init__ is possession.PossessionGate.__init__
            and PrivateGate.checkpoint is possession.PossessionGate.checkpoint
            and PrivateGate._received is possession.PossessionGate._received,
            'C_digest_possession_retained_methods')
        require(PrivateBridgeOwner.__init__ is initialize and PrivateBridgeOwner.activate is activate
            and PrivateBridgeOwner.publish is policy.BridgeOwner.publish
            and PrivateBridgeOwner.summary is policy.BridgeOwner.summary
            and PrivateBridgeOwner.controller_checkpoint is policy.BridgeOwner.controller_checkpoint,
            'C_digest_bridge_method_targets')
        require(base_facade.delivered_peer is validator and base_facade.Owner is PrivateBaseOwner
            and reuse_facade.latest_own_capture is own_capture
            and policy_facade.BridgeOwner is PrivateBridgeOwner
            and policy_facade.run_policy is run_policy and policy_facade.cap_relay_evidence is relay
            and full_facade.verify_case is checker and runner_facade.runner_namespace is runner_namespace,
            'C_digest_facade_targets')
        return {'schema': 'g31.bridge.private_C_digest.routing.v1', 'clones': proofs,
            'same_text_actor_and_C_comparisons_retained': True,
            'old_module_globals_unmodified': True,
            'refresh_all_copies_and_guards_retained': True,
            'own_capture_and_possession_return_copies_retained': True,
            'runner_requirement': 'Original runner factory fresh dict; assess/isolated_base share it and resolve private policy.',
            'C_authority': 'Routing proof alone is not C authority or byte equivalence. Explicit caller must bind accepted Candidate and full dependency checks.',
            'resource_exception_equivalence': False,
            'no_full_saved_acceptance_from_this_proof': True}

    return SimpleNamespace(validator=validator, base=base_facade, reuse=reuse_facade,
        Gate=PrivateGate, BaseOwner=PrivateBaseOwner, BridgeOwner=PrivateBridgeOwner,
        policy=policy_facade, runner_namespace=runner_namespace,
        runner=runner_facade, checker=checker, full=full_facade, prove=prove)


def binder_function(bundle):
    bundle.prove()
    original = previous.binder_function()
    # Preserve same-text replay, original C comparisons and every existing
    # checker/observer transform. Only its two policy-bearing roots differ.
    result = clone(original, {**original.__globals__, 'r': bundle.runner, 'full': bundle.full})
    clone_proof(original, result, {'r': bundle.runner, 'full': bundle.full})
    return result


def bind(plan, redirect, progress, candidate):
    """Actual integration entry; does not load C or weaken the caller's pins."""
    require(type(candidate) is encoder.Candidate, 'C_digest_exact_verified_candidate')
    candidate._verify()
    text_proof = previous.source_proof()
    bundle = _bundle(candidate.capture_digest_v2)
    routing = bundle.prove()
    execute = binder_function(bundle)(plan, redirect, progress)

    def run(directory):
        result, stats = execute(directory)
        candidate._verify()
        bundle.prove()
        # Same final runtime accounting as the original same-text binder.
        bindings = [p for p in stats['ast_proofs']
                    if p.get('schema') == 'g31.bridge.same_text_actor.replay.v1']
        require(len(bindings) == 1, 'C_digest_text_actor_proof_denominator')
        rows = result['replay']['api_rows']
        require(bindings[0]['runtime'] == {'first_row_parses': rows, 'second_actor_parses': rows,
            'pending_texts': 0, 'high_water_texts': 1, 'discarded_on_error': 0, 'instances': 1},
            'C_digest_text_actor_complete_runtime')
        stats['historical_readonly_consumer_proof'] = stats['source_proof']
        stats['source_proof'] = {'same_text_actor': text_proof, 'private_C_digest': routing}
        stats['comparison_restore'] = text_proof['comparison']
        stats['policy_return_deepcopy_retained'] = False
        stats['policy_return_same_text_fresh_parse'] = True
        stats['digest_candidate'] = 'Exact accepted Candidate.capture_digest_v2; original _verify and Unsupported-once dispatcher on every call.'
        stats['prior_actual_C32_review'] = {'path': C32_REVIEW, 'sha256': C32_REVIEW_SHA,
            'scope': 'Two absent inputs, not successful-path/full-stream equivalence authority.'}
        return result, stats

    return run
