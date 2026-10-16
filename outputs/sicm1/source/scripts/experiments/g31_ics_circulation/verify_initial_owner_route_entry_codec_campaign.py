"""All repaired entry saved checks, privately bound to new codec campaign.

This starts from the successful saved-only v2 namespace repair, not the failed
v1 namespace. No original check code or closure is changed; both root predicate
levels and the complete typed entry marker remain mandatory.
"""
from types import SimpleNamespace
from . import verify_initial_owner_route_entry_campaign_v2 as previous
from . import initial_owner_route_entry_codec_campaign as c
from . import initial_owner_route_entry_codec_integration as integration

require, exact = c.require, previous.exact
shared = previous.frozen.shared
NAMES = previous.NAMES
original = previous.frozen.original
_root_original = shared(original.root_replay, {**original.root_replay.__globals__, 'c': c})
_old_facade = SimpleNamespace(**vars(original))
_old_facade.root_replay = _root_original
root_replay = shared(previous.root_replay, {**previous.root_replay.__globals__, 'c': c, 'old': _old_facade})
# Existing marker verifier delegates to the unchanged full query/ACK replay;
# only its private entry integration reference is explicitly retained here.
complete_query_replay = shared(previous.complete_query_replay,
    {**previous.complete_query_replay.__globals__, 'integration': integration.entry})
_namespace = {**previous._namespace, 'c': c, 'root_replay': root_replay,
              'complete_query_replay': complete_query_replay}
for _name in NAMES:
    _namespace[_name] = globals()[_name] = shared(getattr(previous, _name), _namespace)


def source_proof():
    checks = {name: globals()[name] for name in NAMES}
    checks.update(root_replay=root_replay, original_root_replay=_root_original,
                  complete_query_replay=complete_query_replay)
    for name in NAMES:
        current, source = globals()[name], getattr(previous, name)
        require(current.__code__ is source.__code__ and current.__closure__ == source.__closure__ and
            current.__defaults__ == source.__defaults__ and current.__kwdefaults__ == source.__kwdefaults__,
            'entry_codec_saved_check_code_changed:'+name)
    missing = {name: previous.missing_globals(function) for name, function in checks.items()}
    require(all(not values for values in missing.values()), 'entry_codec_saved_missing_defining_globals')
    require(root_replay.__code__ is previous.root_replay.__code__ and
        _root_original.__code__ is original.root_replay.__code__ and
        root_replay.__globals__['c'] is c and _root_original.__globals__['c'] is c and
        root_replay.__globals__['old'].root_replay is _root_original and
        c.contract is integration.contract, 'entry_codec_twolevel_current_predicate')
    require(verify_saved.__globals__ is _namespace and
        verify_saved.__globals__['verify_branch'] is verify_branch and
        verify_branch.__globals__['_original_verify_branch'] is _original_verify_branch and
        _original_verify_branch.__globals__['root_replay'] is root_replay and
        verify_branch.__globals__['complete_query_replay'] is complete_query_replay,
        'entry_codec_saved_shared_namespace')
    return {'schema': 'g31.initial_entry_codec.saved_verifier_source.v1',
        'repaired_namespace_source': previous.source_proof(),
        'all_original_check_codes_defaults_and_closures_identical': True,
        'recursive_LOAD_GLOBAL_missing': missing, 'both_root_replay_levels_new_campaign': True,
        'complete_query_outbox_and_actual_entry_marker_required': True,
        'old_producer_failure_preserved': True, 'native_execution_added': False}
