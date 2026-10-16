"""Version the accepted18 saved reader for the new measured campaign."""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
old=HERE/'verify_owned_C18_saved_root_002.py'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='c147efd5ff6d6458205938a18ca0eba652432ef40b35b00af5de42b9a548c679'
text=old.read_text(encoding='utf8')
changes=(
 ("DEST = OUT/'single_owned_C18_prepare_002'","DEST = ROOT/'outputs/sicm1'"),
 ('4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc','8aa7f63c50310532fa97b0b6251ec118aeae247ff6b072ddbc73edb7f9d3018e'),
 ('root_review_001.json','root_prelaunch_review_001.json'),
 ('de24dfe036794e4e9a83378ccbd99e6ff421a7456d0dabbb8ffda3cf50d0b278','cd7bbb44f7929a5df82874c298f95f8964f9e293688e49ef2dd1946acccb0fed'),
 ('1a80c1e0e9cf82cd2bb1704ea917b51d0c7dc77c12aff9d8a30764dc3703c3e2','f33d1debdde90b47c59f6db13b1c432bb571546a37d499aca2fe46895333298a'),
 ("assert sha(outer['wrapper']) == outer['wrapper_sha256'] == 'ea0dd0c425f32f7c28f0988e35951a9b0b12cd5e4a2160d78c64d9d15f087099'", "assert sha(outer['wrapper']['path']) == outer['wrapper']['sha256'] == 'cd06e16b5f7ad4f24ac42d4f4d4ed8f773bc092434a729bbd5fed8bdb12191a5'"),
 ("for name, digest in outer['artifacts'].items(): assert sha(DEST/name) == digest", "for name, item in outer['artifacts'].items():\n    assert Path(item['path']).resolve() == (DEST/name).resolve(); ref(item)"),
 ("len(plan['source_sha256']) == 218", "len(plan['source_sha256']) == 232"),
 ("sum(row['strictly_improved'] for row in normal.values()) == 1", "sum(row['strictly_improved'] for row in normal.values()) == 2"),
 ("'source_current_and_archive_count': 218", "'source_current_and_archive_count': 232"),
 ("'g31.owned_C18.root_saved_readback.v1'", "'g31.static_inventory_C18.root_saved_readback.v1'"),
 ("raw_outcomes, observed, complete_bytes = {}, [], 0", "raw_outcomes, observed, complete_bytes = {}, [], 0\nroot_intervals = {}"),
 ("    observed.append({'key': key", "    root_intervals[key.replace('/', ':')] = (evidence['root_started_ns'], evidence['root_deadline_ns'], evidence['decision_cutoff_ns'], root['outside_return_ns'])\n    observed.append({'key': key"),
)
for before,after in changes:
    assert text.count(before)==1,before
    text=text.replace(before,after)
before="assert outer['source_changed'] == producer['source_changed'] == []"
after="""frequency,ticks=outer['stopwatch_frequency'],outer['elapsed_ticks']
assert type(frequency) is int and frequency>0 and type(ticks) is int and 0<ticks<=600*frequency
assert outer['python_launch_to_exit_seconds']==ticks/frequency and outer['wrapper_exitcode']==0
assert outer['missing_artifacts']==[] and outer['automatic_retries']==0
"""+before
assert text.count(before)==1;text=text.replace(before,after)
before="report = {'schema':"
extra="""assert sha(DEST/'static_inventory_lifetime.json') == '7e515d40de80e7c942fa5b018d22f93cc9d8d0b102484999756dbef8d5627050'
static = read('static_inventory_lifetime.json')
assert static['status']=='closed_identity_checked' and static['cold_bind_status']=='returned'
assert len(static['constructors'])==18
assert lifetime['setup_started_ns'] <= static['cold_bind_started_ns'] <= static['cold_bind_finished_ns'] <= lifetime['setup_finished_ns']
assert (static['cold_bind_finished_ns']-static['cold_bind_started_ns'])/1e6 == verifier['static_inventory_lifetime']['cold_binding_ms']
constructor_ms=[];seen=set()
for ordinal,row in enumerate(static['constructors']):
    assert row['ordinal']==ordinal and row['status']=='constructor_returned' and row['error_type'] is None
    fields=row['root'];identity=fields['request_id'];assert identity in root_intervals and identity not in seen
    seen.add(identity);start,deadline,cutoff,finish=root_intervals[identity]
    assert (fields['started_ns'],fields['deadline_ns'],fields['cutoff_ns'])==(start,deadline,cutoff)
    assert type(row['started_ns']) is int and type(row['finished_ns']) is int
    assert start <= row['started_ns'] <= row['finished_ns'] <= finish
    elapsed=(row['finished_ns']-row['started_ns'])/1e6;constructor_ms.append(elapsed)
    matched=verifier['static_inventory_lifetime']['rows'][identity.replace(':','/')]
    assert matched=={'status':'constructor_returned','wall_ms':elapsed}
assert seen==set(root_intervals)
assert verifier['static_inventory_lifetime']['missing_before_constructor_failures']==[]
assert verifier['static_inventory_lifetime']['unverified_missing_raw_constructor_rows']=={}
assert verifier['static_inventory_lifetime']['status']=='passed_constructor_sidecar_bound_to_original_saved_checks'
"""
assert text.count(before)==1;text=text.replace(before,extra+before)
before="    'closed_roots': 16, 'unknown_roots': 2, 'observed_under100': 0,"
after=before+"\n    'constructor_nested_wall_ms': {'min': min(constructor_ms), 'median': statistics.median(constructor_ms), 'max': max(constructor_ms), 'sum': sum(constructor_ms)},\n    'cold_static_bind_ms': verifier['static_inventory_lifetime']['cold_binding_ms'],"
assert text.count(before)==1;text=text.replace(before,after)
target=HERE/'verify_sicm1_saved_root_001.py'
with target.open('x',encoding='utf8') as f:f.write(text)
print({'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
