import gzip
import pytest
from scripts.experiments.g31_ics_circulation import validate_live_communication_lazy as d

def test_fresh96_old73_comparison_domain():
    rows={f'row{i:02d}':{'status':'exact_conformance','prediction':{'path':str(i),'sha256':'x'}}
        if i<73 else {'status':'unknown_unexecuted'} for i in range(96)}
    assert len(d.saved_prefix(rows))==73
    rows.pop('row95')
    with pytest.raises(ValueError):d.saved_prefix(rows)

def test_old_unknown_cannot_be_promoted_in_reused_reference():
    rows={str(i):{'status':'exact_conformance','prediction':{}} if i<74 else {'status':'unknown_unexecuted'} for i in range(96)}
    with pytest.raises(ValueError):d.saved_prefix(rows)

def test_complete_prediction_comparison_keeps_order_and_float_spelling():
    encoded=lambda text:gzip.compress(text.encode(),mtime=0)
    assert d.exact_output_bytes(encoded('{"at":1.0,"rows":[1,2]}'),encoded('{"at":1.0,"rows":[1,2]}'))
    assert not d.exact_output_bytes(encoded('{"at":1.0}'),encoded('{"at":1}'))
    assert not d.exact_output_bytes(encoded('{"rows":[1,2]}'),encoded('{"rows":[2,1]}'))

def test_budget_is_explicit_offline_shared360():
    assert d.LIMIT==360. and 'lazy' in d.MODULE
