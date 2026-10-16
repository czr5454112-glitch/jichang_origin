import copy
import math
import pytest

from scripts.experiments.g31_ics_circulation import protocol_query_copy as m
from scripts.experiments.g31_ics_circulation import protocol_control as control


def view(extra="kind",ack=True):
    result={"request_id":"live:1:A:x:0","status":"acknowledged","attempt":2,extra:"fixture"}
    if ack:result["last_delivered_ack"]={"sequence":3,"status":"received","observed_at":.1,"delivered_at":.2}
    return result


@pytest.mark.parametrize("extra",["kind","physical_resolution"])
@pytest.mark.parametrize("ack",[False,True])
def test_supported_double_copy_has_exact_order_and_complete_mutation_isolation(extra,ack):
    source=view(extra,ack);a=m.query_view_copy(source);b=m.query_view_copy(source)
    assert a==b==copy.deepcopy(source) and list(a)==list(source) and a is not b and a is not source
    a["status"]="changed";assert source["status"]==b["status"]=="acknowledged"
    if ack:
        assert a["last_delivered_ack"] is not b["last_delivered_ack"] and a["last_delivered_ack"] is not source["last_delivered_ack"]
        a["last_delivered_ack"]["status"]="changed";assert source["last_delivered_ack"]["status"]==b["last_delivered_ack"]["status"]=="received"
        source["last_delivered_ack"]["status"]="source_changed";assert b["last_delivered_ack"]["status"]=="received"


@pytest.mark.parametrize("atom",[None,True,0,0.,-0.,1,1.,float("nan"),float("inf"),"中文"])
def test_immutable_atom_identity_matches_deepcopy(atom):
    source=view();source["last_delivered_ack"]["value"]=atom
    assert m.query_view_copy(source)["last_delivered_ack"]["value"] is copy.deepcopy(source)["last_delivered_ack"]["value"]


@pytest.mark.parametrize("mode",["nested","alias","cycle","custom_value","custom_dict","custom_key","unknown_field","memo"])
def test_unsupported_structure_delegates_to_standard_copy_once(monkeypatch,mode):
    source=view();memo=None
    class Custom:
        def __deepcopy__(self,memo):return "copied_custom"
    class Dict(dict):pass
    if mode=="nested":source["last_delivered_ack"]["body"]={"rows":[1]}
    elif mode=="alias":source["other_ack"]=source["last_delivered_ack"]
    elif mode=="cycle":source["last_delivered_ack"]["self"]=source
    elif mode=="custom_value":source["last_delivered_ack"]["value"]=Custom()
    elif mode=="custom_dict":source=Dict(source)
    elif mode=="custom_key":source[Custom()]=1
    elif mode=="unknown_field":source["new_future_field"]=1
    else:memo={}
    actual_deepcopy=copy.deepcopy;calls=[]
    class Facade:
        @staticmethod
        def deepcopy(value,memo=None):calls.append(value);return actual_deepcopy(value,memo)
    monkeypatch.setattr(m,"standard_copy",Facade)
    result=m.query_view_copy(source,memo)
    assert len(calls)==1 and calls[0] is source
    if mode=="alias":assert result["other_ack"] is result["last_delivered_ack"]
    if mode=="cycle":assert result["last_delivered_ack"]["self"] is result
    if mode=="custom_value":assert result["last_delivered_ack"]["value"]=="copied_custom"


def test_context_never_changes_standard_library_copy_and_restores_on_failure():
    original=copy.deepcopy
    with pytest.raises(RuntimeError,match="fixture"):
        with m.installed_query_view_copy():
            assert copy.deepcopy is original and control.copy.deepcopy is m.query_view_copy
            with pytest.raises(ValueError,match="another_facade"):
                with m.installed_query_view_copy():pass
            raise RuntimeError("fixture")
    assert control.copy is copy and copy.deepcopy is original
