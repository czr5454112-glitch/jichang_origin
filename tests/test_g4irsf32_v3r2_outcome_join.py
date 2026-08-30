from __future__ import annotations
import copy
import pytest
from czr005 import g4irsf32_v3r2_outcome_join as joiner

def _episode(bag: int, start: float, end: float, seq: int, **identity: int | float) -> dict:
    return {'case_id': 'case-a', 'runtime_bag_id': bag, 'node': 4, 'actual_L_service_start': start, 'actual_L_service_complete': end, 'completion_event_seq': seq, 'actual_subsequent_source_wait': 0.0, 'actual_subsequent_junction_wait': 0.0, 'actual_transit_seconds': 0.0, 'actual_subsequent_calendar_wait': 0.0, 'actual_subsequent_wait': 0.0, **identity}

def _row(*, path: int=1, ordinal: int=1, opportunity: int=101) -> dict:
    direct = path == 1
    return {'case_id': 'case-a', 'observation_ordinal': ordinal, 'opportunity_id': opportunity, 'event_time': 10.0, 'event_seq': 100, 'node': 4, 'calendar_generation_before': 22, 'seam_kind_code': path, 'external_path_code': path, 'external_task_id': 90, 'external_runtime_bag_id': 9, 'external_upstream_node': 3, 'external_slot_start_seconds': 12.0, 'external_slot_end_seconds': 14.0, 'external_service_seconds': 2.0, 'external_projected_arrival': 12.0, 'has_direct_episode_identity': direct, 'external_direct_episode_event_seq': 105 if direct else 0, 'has_j2_identity': not direct, 'external_request_id': 0 if direct else 401, 'external_request_lineage': 0 if direct else 501, 'external_request_generation': 0 if direct else 2, 'external_junction_queue_generation': 0 if direct else 3, 'local_task_id': 70, 'local_runtime_bag_id': 7, 'local_service_seconds': 2.0, 'L0': 10.0, 'X_insert': 2.0, 'H_gap': 0.0, 'epsilon': 1e-09}

def _episodes(*, path: int=1) -> list[dict]:
    identity = {'direct_commit_event_seq': 105} if path == 1 else {'request_id': 401, 'request_lineage': 501, 'request_generation': 2, 'junction_queue_generation': 3, 'slot_node': 4, 'slot_start': 12.0, 'slot_end': 14.0, 'slot_calendar_generation_before': 22}
    external = _episode(9, 12.0, 14.0, 180, **identity)
    external['actual_subsequent_source_wait'] = -3.0
    external['actual_subsequent_wait'] = 999.0
    return [_episode(7, 2.0, 4.0, 80), _episode(8, 10.0, 11.0, 130), external, _episode(7, 15.0, 17.0, 200), _episode(7, 20.0, 22.0, 300)]

def _pair(result: dict) -> dict:
    return result['pairs'][0]

def _independent_repeat() -> tuple[dict, dict]:
    row = _row(ordinal=2, opportunity=102)
    row.update(event_time=10.1, event_seq=101, external_task_id=91,
               external_runtime_bag_id=10, external_slot_start_seconds=18.0,
               external_slot_end_seconds=20.0, external_projected_arrival=18.0,
               external_direct_episode_event_seq=106)
    episode = _episode(10, 18.0, 20.0, 280, direct_commit_event_seq=106)
    return row, episode

def test_direct_join_derives_v3r2_estimand_and_wait_union() -> None:
    result = joiner.join_v3r2_outcomes([_row()], _episodes())
    pair = _pair(result)
    assert result['status'] == joiner.JOINED
    assert pair['local']['actual_L_service_start'] == 15.0
    assert pair['local']['actual_subsequent_calendar_wait'] == 3.0
    assert pair['local']['actual_subsequent_source_wait'] == 2.0
    assert pair['local']['actual_subsequent_wait'] == 5.0
    assert (pair['Y_realized'], pair['A_gap']) == (5.0, 3.0)
    assert (pair['X_insert'], pair['H_gap']) == (2.0, 0.0)
    assert pair['external']['actual_subsequent_wait'] == 999.0

def test_j2_requires_full_identity_slot_and_generation() -> None:
    assert _pair(joiner.join_v3r2_outcomes([_row(path=2)], _episodes(path=2)))['status'] == joiner.JOINED
    wrong = _episodes(path=2)
    wrong[2]['request_lineage'] = 999
    assert _pair(joiner.join_v3r2_outcomes([_row(path=2)], wrong))['reason'] == 'EXTERNAL_EPISODE_NOT_UNIQUE'
    missing = _row(path=2)
    del missing['external_request_lineage']
    try:
        joiner.join_v3r2_outcomes([missing], _episodes(path=2))
    except joiner.OutcomeJoinError as error:
        assert 'external_request_lineage' in str(error)
    else:
        raise AssertionError('missing J2 physical identity must fail closed')

def test_ambiguous_external_or_local_identity_fails_case_closed() -> None:
    direct = _episodes()
    direct.append(copy.deepcopy(direct[2]))
    assert _pair(joiner.join_v3r2_outcomes([_row()], direct))['reason'] == 'EXTERNAL_EPISODE_NOT_UNIQUE'
    no_local = [episode for episode in _episodes() if not (episode['runtime_bag_id'] == 7 and episode['completion_event_seq'] > 100)]
    assert _pair(joiner.join_v3r2_outcomes([_row()], no_local))['reason'] == 'LOCAL_NEXT_EPISODE_MISSING'
    duplicate = _episodes()
    duplicate.append(copy.deepcopy(duplicate[3]))
    assert _pair(joiner.join_v3r2_outcomes([_row()], duplicate))['reason'] == 'LOCAL_NEXT_EPISODE_AMBIGUOUS'

def test_negative_y_or_wrong_duration_invalidates_entire_case() -> None:
    negative = _row()
    negative['L0'] = 16.0
    result = joiner.join_v3r2_outcomes([negative], _episodes())
    assert _pair(result)['reason'] == 'NEGATIVE_LOCAL_WAIT_OR_REALIZED_MARGIN'
    assert result['case_status']['case-a'] == joiner.INVALID
    wrong = _row()
    wrong['local_service_seconds'] = 3.0
    assert _pair(joiner.join_v3r2_outcomes([wrong], _episodes()))['reason'] == 'CANDIDATE_IDENTITY_SLOT_OR_DURATION'

def test_outcome_blind_bag_repeat_and_episode_reuse_are_distinct() -> None:
    repeated, independent_episode = _independent_repeat()
    result = joiner.join_v3r2_outcomes(
        [repeated, _row()], [*_episodes(), independent_episode]
    )
    assert [pair['status'] for pair in result['pairs']] == [joiner.JOINED, joiner.REPEAT_DIAGNOSTIC]
    reused = _episodes()
    reused[3]['completion_event_seq'] = reused[2]['completion_event_seq']
    pair = _pair(joiner.join_v3r2_outcomes([_row()], reused))
    assert (pair['status'], pair['reason']) == (joiner.INVALID, 'PAIR_REUSES_SERVICE_EPISODE')

@pytest.mark.parametrize(
    ('failure', 'reason'),
    [('missing', 'EXTERNAL_EPISODE_NOT_UNIQUE'),
     ('slot_mismatch', 'EXTERNAL_PROVENANCE_SLOT_OR_DURATION')],
)
def test_repeat_with_invalid_external_provenance_invalidates_entire_case(
    failure: str, reason: str
) -> None:
    repeated, independent_episode = _independent_repeat()
    episodes = _episodes()
    if failure == 'slot_mismatch':
        independent_episode['actual_L_service_start'] = 18.5
        episodes.append(independent_episode)
    result = joiner.join_v3r2_outcomes([repeated, _row()], episodes)
    assert [pair['status'] for pair in result['pairs']] == [
        joiner.JOINED, joiner.INVALID
    ]
    assert result['pairs'][1]['reason'] == reason
    assert result['pairs'][1]['primary'] is False
    assert result['status'] == joiner.INVALID
    assert result['case_status'] == {'case-a': joiner.INVALID}

def test_frozen_epsilon_and_duplicate_physical_commit_fail_closed() -> None:
    loose = _row()
    loose['epsilon'] = 1.0
    try:
        joiner.join_v3r2_outcomes([loose], _episodes())
    except joiner.OutcomeJoinError as error:
        assert 'frozen 1e-9' in str(error)
    else:
        raise AssertionError('self-reported loose epsilon must fail closed')
    duplicate = _row(ordinal=2, opportunity=102)
    duplicate.update(external_slot_start_seconds=12.0 + 0.5e-9, external_slot_end_seconds=14.0 + 0.5e-9)
    try:
        joiner.join_v3r2_outcomes([_row(), duplicate], _episodes())
    except joiner.OutcomeJoinError as error:
        assert 'duplicate physical commit identity' in str(error)
    else:
        raise AssertionError('one physical commit cannot become two observations')

def test_direct_and_j2_cannot_claim_the_same_external_service_episode() -> None:
    episodes = _episodes()
    episodes[2].update(
        request_id=401,
        request_lineage=501,
        request_generation=2,
        junction_queue_generation=3,
        slot_node=4,
        slot_start=12.0,
        slot_end=14.0,
        slot_calendar_generation_before=22,
    )
    j2 = _row(path=2, ordinal=2, opportunity=102)
    with pytest.raises(
        joiner.OutcomeJoinError,
        match='duplicate external service episode across observation seams',
    ):
        joiner.join_v3r2_outcomes([_row(), j2], episodes)

def test_join_accepts_generic_service_node_and_rejects_non_scalar_input() -> None:
    row = _row()
    row['node'] = 7
    episodes = _episodes()
    for episode in episodes:
        episode['node'] = 7
    assert _pair(joiner.join_v3r2_outcomes([row], episodes))['status'] == joiner.JOINED
    bad = _row()
    bad['event_seq'] = True
    try:
        joiner.join_v3r2_outcomes([bad], _episodes())
    except joiner.OutcomeJoinError:
        pass
    else:
        raise AssertionError('bool event_seq must fail closed')
