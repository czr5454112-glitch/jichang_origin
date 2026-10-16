"""Record completed source reviews and inspect pins/XML; no model execution."""
from pathlib import Path
import hashlib, json, time, xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def check(ok,why):
    if not ok:raise ValueError(why)
def write(p,value):
    with p.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'path':str(p),'sha256':sha(p)}))
def xml(p,n):
    rows=ET.parse(p).getroot().findall('.//testcase')
    check(len(rows)==n and not any(c.tag in ('failure','error','skipped') for r in rows for c in r),'XML gate')

def main():
    start=time.perf_counter();case=OUT/'json_prediction_RPC_prepare_002';pins={}
    def pin(p,expected=None):
        value=sha(p);check(expected is None or value==expected,'hash:'+str(p));pins[str(p)]=value
    pin(case/'ready.json','84ded34a92809a98819e60ce55eda60ec69999690ae49d08bcb2a727a449e1ab')
    pin(case/'preregistered_protocol.json','c30af2fa76ec3cb57d5fa627f7daf6b419bbdbb863c3ff8e384626880dd35d06')
    plan=read(case/'preregistered_protocol.json');check(len(plan['source_sha256'])==85,'closure count')
    for name,digest in plan['source_sha256'].items():pin(ROOT/name,digest);pin(case/'source'/name,digest)
    pin(case/'image/manifest.json',plan['image']['version']);image=read(case/'image/manifest.json')
    for name,digest in image['files'].items():pin(case/'image'/name,digest);check(plan['source_sha256'][name]==digest,'image vs archive')
    for name,digest in plan['pure_gate'].items():pin(name,digest)
    pure=OUT/'json_prediction_worker_pure_005';pin(pure/'tests.xml','6248a5fc1d299898850965bec761d25c844cb015efa2cd194e4194038d7e7d62');xml(pure/'tests.xml',80)
    for mode,gate in plan['startup_gate'].items():
        ref=gate['reference'];pin(ref['path'],ref['sha256']);a=read(ref['path'])
        check(a['version']==plan['image']['version'] and a['mode']==mode and a['source_unchanged'] is True and a['closed_requests']==0,'startup identity')
        check(a['loaded_sources']==gate['loaded_sources'] and a['proof']==gate['proof'],'complete source/proof binding')
        check(all(image['files'][k]==v for k,v in a['loaded_sources'].items()),'loaded source image')
    check(plan['startup_gate']['reference']['loaded_sources']==plan['startup_gate']['compiled']['loaded_sources'],'same loaded closure')
    write(case/'independent_source_review_001.json',{
        'status':'source_review_closed_no_concrete_blocker','evidence_sha256':pins,'live_and_archived_source_count':85,
        'saved_pure_tests_inspected':80,'tests_rerun':0,'new_prediction_calls':0,'native_calls':0,'performance_campaign_launched_by_reviewer':False,
        'reviewed':['Private constructor retains original dynamic isolation, full input guard, fingerprint, potential, same-input full baseline, every typed action guard and all32 candidate evaluations.',
            'Exactly two implementation checks and guard compilation move to fixed-image startup. Source code/global modules are not monkeypatched; private closure and class-name slot mangling are retained.',
            'Strict JSON/version/sequence/request IDs cannot name callbacks/modules/code. Each request creates independent context; only verified compiled code survives requests.',
            'Verified byte loader, -I -S process, no new project imports after READY, source recheck at close, caller pipe/codec/bookkeeping envelope and close/reclamation costs remain.',
            'Owned Job assignment precedes release; watchdog closes blocked pipe worker, outer owned120 includes campaign descendants; separate external wall includes interpreter/export.',
            'Prior saved READY subset/proof omission finding is closed: exact loaded maps and full proofs are bound to zero-request functional startup/close attestations of the same image. Deletion/changed-proof negatives are present.'],
        'limits':['Operational immutable-image contract, not a hostile filesystem security sandbox; startup inspect may read the archived file again and close rehash detects persistent drift.',
            'Functional saved XML inspected, not rerun; no performance or complete business-request100ms claim. Cold startup/shutdown remain separately retained, not amortized.'],
        'wall_seconds_for_pin_and_XML_recording':time.perf_counter()-start})
    pins={}
    for name in ('scripts/experiments/g31_ics_circulation/current_empty_possession_permit.py','tests/test_g31_circulation_current_possession_permit.py',
                 'scripts/experiments/g31_ics_circulation/research_original_low_wip.py','scripts/experiments/g31_ics_circulation/research_original_low_wip_reuse.py'):
        pin(ROOT/name)
    pin(OUT/'possession_gate_tests_002.xml');xml(OUT/'possession_gate_tests_002.xml',24)
    write(OUT/'current_possession_permit_independent_source_review_001.json',{
        'status':'source_review_closed_no_concrete_blocker_in_declared_cooperative_scope','evidence_sha256':pins,
        'saved_pure_tests_inspected':24,'tests_rerun':0,'native_calls':0,'controller_integration_reviewed':False,
        'reviewed':['Exact current local token empty state, node ownership, no job/edge/reception and availability guard; own delivered native selfcopy matches node/generation/traversal/availability and newest valid peer follows own capture.',
            'Own actual outbox payloads bind each post-parking transfer to token and parking payloads to declared rows; own selfcopy action identity set equals current complete own transfer set.',
            'Both owners source-authored action rows have actual received ACK status; pending/rejected/expired/undeclared action states cannot grant.',
            'Exact strictly increasing frozen action-ID set consumed before permit return; duplicate ACK changes or same-cardinality replacement do not reauthorize. Returned copies/checkpoint do not mutate consumed set.',
            'No opaque peer ID is parsed as payload; no EMPTY_RECEIVED or completed-job receipt is fabricated.'],
        'integration_requirements':['Caller must supply fresh actual same-session current view and immutable actual outbox; this pure gate alone cannot authenticate arbitrary caller dictionaries.',
            'Both cooperating owners must restrict all post-parking physical actions to the designated token and admit at most one outstanding transfer; peer rows do not prove remote payload or absence of future unsubmitted plans.',
            'Persist consumed watermarks with actual client state, disallow reset/reuse after crash without an explicit recovery contract, then perform native source/receiver revalidation before operation installation.',
            'No public active_leg field is invented. Current empty/no-edge/no-reception is a guarded public prerequisite; final native actual validation remains required.'],
        'remote_payload_or_arrival_causality_certified':False,'original_business_100ms_certified':False})
if __name__=='__main__':main()
