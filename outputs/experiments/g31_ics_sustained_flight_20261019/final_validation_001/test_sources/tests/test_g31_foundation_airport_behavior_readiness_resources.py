"""Resource revision gates only; no full callback reads or fitting."""
import json
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_readiness as readiness


def fixture(tmp_path):
    collection=tmp_path/'collection'
    prereg={'path':'original_immutable_contract','sha256':'unchanged'}
    plan={'collection':str(collection.resolve()),'minimum':readiness.MINIMUM,
        'training_contract':readiness.evidence.training_contract(collection.name),
        'inputs':{'preregistration':prereg},'soft_wall_seconds':180}
    path=tmp_path/'previous_plan.json';path.write_text(json.dumps(plan))
    receipt={'plan':readiness.ref(path),'status':'failed_behavior_readiness','fit_calls':0,'native_branches':0,
        'exception':'Traceback preserved\nValueError: airport_behavior_evidence:readiness_wall_budget\n'}
    rpath=tmp_path/'previous_receipt.json';rpath.write_text(json.dumps(receipt))
    revision={'scope':'read_only_wall_budget_only','soft_wall_seconds':660,'hard_wall_seconds':720,
        'automatic_retries':0,'criterion_unchanged':True,'fit_calls':0,'native_branches':0,
        'evidence':{'previous_plan':readiness.ref(path),'previous_receipt':readiness.ref(rpath)}}
    return collection,prereg,revision


def test_resource_revision_preserves_original_budget_by_default(tmp_path):
    collection,prereg,revision=fixture(tmp_path)
    assert readiness.resource_budget(None,collection=collection,preregistration=prereg)==(180,210)
    assert readiness.resource_budget(revision,collection=collection,preregistration=prereg)==(660,720)


@pytest.mark.parametrize('change',['soft','outer','retry','criterion','fit','native','collection','prereg','not_budget_failure','tampered_evidence'])
def test_resource_revision_rejects_any_other_change(tmp_path,change):
    collection,prereg,revision=fixture(tmp_path)
    if change in ('soft','outer','retry','criterion','fit','native'):
        key={'soft':'soft_wall_seconds','outer':'hard_wall_seconds','retry':'automatic_retries',
             'criterion':'criterion_unchanged','fit':'fit_calls','native':'native_branches'}[change]
        revision[key]={'criterion':False}.get(change,1)
    elif change=='collection':collection=tmp_path/'other'
    elif change=='prereg':prereg={'path':'changed','sha256':'changed'}
    else:
        path=revision['evidence']['previous_receipt']['path']
        receipt=readiness.read(path);receipt['exception']='different actual exception'
        with open(path,'w')as stream:json.dump(receipt,stream)
        if change=='not_budget_failure':revision['evidence']['previous_receipt']=readiness.ref(path)
    with pytest.raises(ValueError):readiness.resource_budget(revision,collection=collection,preregistration=prereg)
