import copy
import pytest
from scripts.experiments.g31_ics_circulation import diagnose_live_communication_partial as d

def rows():
    return {k:{'status':'exact_conformance' if i<73 else 'unknown_unexecuted',
        **({'model_wall_seconds':1.} if i<73 else {})} for i,k in enumerate(d.comparison.ORDER)}

def test_partial_preserves_full_denominator():
    known,unknown=d.classify(rows())
    assert len(known)==73 and len(unknown)==23 and unknown[0]=='insufficient_advance/vector_09'

def test_missing_row_cannot_close_denominator():
    value=rows();value.pop('insufficient_advance/vector_31')
    with pytest.raises(ValueError):d.classify(value)

def test_costs_do_not_assign_residual_to_one_stage():
    value=d.cost_summary(rows(),100.)
    assert value['saved_model_seconds']==73. and value['unpartitioned_seconds']==27.
    assert 'in-flight' in value['unpartitioned_scope']

def test_exact_values_preserve_float_bits_and_types():
    assert not d.comparison.exact(1.,1)
    assert not d.comparison.exact(1.,1.0000000000000002)
    assert d.comparison.exact({'a':[1.,2.]},copy.deepcopy({'a':[1.,2.]}))
