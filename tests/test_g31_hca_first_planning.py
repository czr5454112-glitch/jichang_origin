"""The first attempt is observed independently of successful path admission."""
import copy
import pytest
from scripts.experiments.g31_no_wait.hca_first_planning import annotate, reconstruct, full_population_means


def fixture():
    canonical=[dict(segment_id='0:direct',task_id=0,leg='direct',start=1,goal=2,pass_time=10.25),
               dict(segment_id='1:direct',task_id=1,leg='direct',start=1,goal=2,pass_time=80.0)]
    bags=[dict(segment_id='0:direct',task_id=0,start=1,goal=2,release_time=11.0,admission=16.0,
               finish=25.5,observed_finish=26.0,completed=True,route=[[1,16.0,18.0],[2,25.5,27.5]]),
          dict(segment_id='1:direct',task_id=1,start=1,goal=2,release_time=None,admission=None,
               finish=None,completed=False)]
    releases=[dict(task_id=0,start=1,goal=2,release_epoch=11.0)]
    return canonical,bags,releases


def test_retry_is_in_tht_and_preplanning_hold_is_separate():
    rows=reconstruct(*fixture())
    assert rows[0]['first_attempt_time']==11.0
    assert rows[0]['successful_admission_time']==16.0
    assert rows[0]['planning_retry_wait_seconds']==5.0
    assert rows[0]['canonical_hold_seconds']==0.75
    assert rows[0]['tht_from_first_planning_seconds']==14.5
    assert rows[0]['network_after_success_seconds']==9.5


def test_unreleased_preserves_full_population_and_nulls():
    rows=annotate(*fixture())
    assert len(rows)==2
    assert rows[1]['first_planning_attempt_time'] is None
    assert rows[1]['preplanning_source_hold_seconds'] is None
    assert all('activation_time' not in row for row in rows)


def test_unfinished_population_never_averages_only_completed_bags():
    rows=reconstruct(*fixture())
    assert all(value is None for value in full_population_means(rows).values())
    assert full_population_means(rows[:1])['tht_from_first_planning_seconds']==14.5


def test_annotation_preserves_every_original_field_without_mutation():
    canonical,bags,releases=fixture();before=copy.deepcopy(bags)
    output=annotate(canonical,bags,releases)
    assert bags==before
    assert all(all(new[k]==v for k,v in old.items()) for old,new in zip(before,output))
    assert output[0]['first_planning_attempt_time']==11.0


@pytest.mark.parametrize('failure', ['missing_release','release_mismatch','early_release','admission_before_attempt',
                                    'duplicate_release','identity_mismatch','missing_bag','double_annotation'])
def test_rejects_unsupported_or_ambiguous_start(failure):
    canonical,bags,releases=fixture()
    if failure=='missing_release': releases=[]
    elif failure=='release_mismatch': releases[0]['release_epoch']=12.0
    elif failure=='early_release': releases[0]['release_epoch']=10.0;bags[0]['release_time']=10.0
    elif failure=='admission_before_attempt': bags[0]['admission']=10.5
    elif failure=='duplicate_release': releases.append(dict(releases[0]))
    elif failure=='identity_mismatch': bags[0]['goal']=3
    elif failure=='missing_bag': bags.pop()
    elif failure=='double_annotation': bags[0]['first_planning_attempt_time']=11.0
    with pytest.raises(ValueError): annotate(canonical,bags,releases)
