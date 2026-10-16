from copy import deepcopy
import math
import pytest

import test_g31_circulation_regional_path_pool as previous
from scripts.experiments.g31_ics_circulation import regional_path_pool as old
from scripts.experiments.g31_ics_circulation import regional_path_bytes as new

# Run the exact previous 52 differential cases against the new key. The old
# file and its function globals remain unchanged; its module reference resolves
# the process-local key override only for that test's fixture lifetime.
globals().update({name:value for name,value in vars(previous).items() if name.startswith("test_")})

@pytest.fixture(autouse=True)
def candidate_for_inherited_cases(request,monkeypatch):
    if request.node.function.__module__==previous.__name__:
        monkeypatch.setattr(old,"public_routing_key",new.public_routing_bytes)


@pytest.mark.parametrize("value",[0,0.,-0.,1,1.,-1.,2**53,-2**53,math.nextafter(1.,2.),1e-300,1e300])
def test_exact_numeric_encodings_distinct_and_alias_independent(value):
    obs=previous.observation();obs["node_contracts"][1]["occupancy"]=value
    key=new.public_routing_bytes(obs)
    assert key is not None and type(key[0]) is bytes
    assert new.public_routing_bytes(deepcopy(obs))==key
    for alternate in [0,0.,-0.,1,1.,-1.,2**53,-2**53,math.nextafter(1.,2.),1e-300,1e300]:
        other=deepcopy(obs);other["node_contracts"][1]["occupancy"]=alternate
        assert (new.public_routing_bytes(other)==key)==(new.ORIGINAL_KEY(other)==new.ORIGINAL_KEY(obs))


@pytest.mark.parametrize("value",[True,False,float("nan"),float("inf"),float("-inf"),2**53+1,-2**53-1,"0",None])
def test_numeric_domain_matches_previous_rejection(value):
    obs=previous.observation();obs["node_contracts"][1]["occupancy"]=value
    assert new.public_routing_bytes(obs) is None and new.ORIGINAL_KEY(obs) is None


def test_custom_reducer_is_never_called_even_when_pickle_is_available():
    class Trap(float):
        def __reduce_ex__(self,*args):raise AssertionError("custom reducer executed")
    obs=previous.observation();obs["node_contracts"][1]["occupancy"]=Trap(0.)
    assert new.public_routing_bytes(obs) is None
    obs=previous.observation();obs["jobs"].append(Trap(0.))
    assert new.public_routing_bytes(obs) is not None  # unused payload never encoded


def test_context_factory_key_cleanup_and_nested_rejection():
    factory=old.protocol_control._ObservationRouting
    with pytest.raises(RuntimeError,match="fixture"):
        with new.installed_regional_path_bytes() as pool:
            obs=previous.observation();assert pool.handle(obs).path(obs,0,3)==(0,1,3)
            with pytest.raises(ValueError,match="another_key_installation"):
                with new.installed_regional_path_bytes():pass
            raise RuntimeError("fixture")
    assert old.public_routing_key is new.ORIGINAL_KEY and old.protocol_control._ObservationRouting is factory
    assert pool.snapshot()["resident_paths"]==0
