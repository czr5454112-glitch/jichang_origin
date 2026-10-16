"""Raw gate relationship guards; phase algorithm has separate exact ABI tests.

These fixtures deliberately mock the partition result, so they are NOT runtime
acceptance evidence. They isolate tape/domain/seal/outcome/overflow invariants.
"""
from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation import native025_timing_gate as gate


def fixture(monkeypatch):
    records={}
    for arm,cases in gate.ARMS.items():
        records[arm]={}
        for case in cases:
            outputs=[];envelopes=[]
            for name in gate.endpoints(case):
                args=([{'request_id':'request'}] if name.startswith('submit_protocol_') else
                      ['A','request'] if name in {'protocol_command','protocol_request'} else [])
                expected=('updated' if case=='route_allowed' else 'rejected' if case in
                    {'route_stale','source_refused','receiver_refused','cancel_committed'} else
                    'cancelled' if case=='cancel_pending' else 'delivered' if case=='forecast_withdraw' or
                    case.startswith('planning_snapshot') else 'received')
                result={'last_delivered_ack':{'status':expected,'reason':'allowed' if case=='route_allowed' else 'stale_executed_prefix'}}
                entry={'endpoint':name,'args':args,'kwargs':{},'returned':result};outputs.append(entry)
                e={'api_endpoint':name,'method':gate.abi.legacy.METHODS.index(gate.abi.ENDPOINTS025[name])}
                if name.startswith('submit_protocol_') or name in {'protocol_command','protocol_request'}: e['protocol_request_id']='request'
                envelopes.append(e)
            if case=='exception': outputs[0]={'endpoint':'advance_to','args':[-1.], 'exception':{'type':'ValueError'}}
            row={'case':case,'status':'captured','input':gate.scene(case),'outputs':outputs,
                'native_seal':'a'*64,'checkpoint_seal':'a'*64}
            if arm=='native025_timed':
                phases=('source_execution','ack_create','ack_delivery','publication_delivery')
                row['timing']={'batches':[{'rows':[{'phase':gate.PHASES.index(p),'identity_kind':10 if case in gate.V2_CASES else 0} for p in phases],
                    'errors':1 if case=='overflow' else 0,'command_identities':[{'kind':'planning_snapshot_v2'}]}],
                    'envelopes':envelopes,'capture_errors':['ValueError'] if case=='exception' else []}
                if case=='exception': row['timing']['batches'][0]['exception_fixture']=True
            records[arm][case]=row
    monkeypatch.setattr(gate.abi,'analyze_candidate_partition',lambda b,e:{'status':'unknown' if b[0]['errors'] or b[0].get('exception_fixture') else 'structurally_valid_native025_candidate_partition'})
    return records


def test_complete_closed_domain_relationships(monkeypatch):
    assert all(gate.check_records(fixture(monkeypatch)).values())


@pytest.mark.parametrize('defect',['missing_case','wrong_input','empty_all_tapes','reordered_tape','missing_envelope',
    'wrong_envelope_id','null_seals','different_seal','wrong_outcome','v2_wrong_tag','v2_wrong_endpoint','wrong_overflow_error','negative_claimed_valid'])
def test_raw_relationship_tampering_fails_closed(monkeypatch,defect):
    data=fixture(monkeypatch);case='normal';timed=data['native025_timed'][case]
    if defect=='missing_case': del data['native022_plain'][case]
    elif defect=='wrong_input':
        for arm in gate.ARMS: data[arm][case]['input']['jobs']=[]
    elif defect=='empty_all_tapes':
        for arm in gate.ARMS: data[arm][case]['outputs']=[]
    elif defect=='reordered_tape': timed['outputs'][0],timed['outputs'][1]=timed['outputs'][1],timed['outputs'][0]
    elif defect=='missing_envelope': timed['timing']['envelopes'].pop()
    elif defect=='wrong_envelope_id': timed['timing']['envelopes'][1]['protocol_request_id']='foreign'
    elif defect=='null_seals':
        for arm in gate.ARMS: data[arm][case]['native_seal']=data[arm][case]['checkpoint_seal']=None
    elif defect=='different_seal': timed['native_seal']='b'*64
    elif defect=='wrong_outcome': timed['outputs'][-2]['returned']['last_delivered_ack']['status']='pending'
    elif defect=='v2_wrong_tag':
        for r in data['native025_timed']['planning_snapshot_v2']['timing']['batches'][0]['rows']:r['identity_kind']=9
    elif defect=='v2_wrong_endpoint':data['native025_timed']['planning_snapshot_v2']['timing']['envelopes'][-2]['api_endpoint']='protocol_planning_snapshots'
    elif defect=='wrong_overflow_error':data['native025_timed']['overflow']['timing']['batches'][0]['errors']=2
    else:monkeypatch.setattr(gate.abi,'analyze_candidate_partition',lambda b,e:{'status':'structurally_valid_native025_candidate_partition'})
    with pytest.raises(ValueError):gate.check_records(data)
