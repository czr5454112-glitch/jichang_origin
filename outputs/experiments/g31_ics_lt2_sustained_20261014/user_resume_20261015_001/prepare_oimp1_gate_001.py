"""Create new gate source only, from reviewed retained-policy owned harness."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CODE = ROOT / 'scripts/experiments/g31_ics_circulation'
OUT = HERE.parent

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def replace(text, old, new, count=1):
    assert text.count(old) == count, (old, text.count(old), count)
    return text.replace(old, new)
def create(path, text):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(text)

source = CODE / 'run_live_obligation_online_retained_policy_pure.py'
wrapper = OUT / 'control_timers_lorp1_pure_001.ps1'
assert sha(source) == '47866a2db3e838ca40fb9f53719d13a6b0c48ffe448cdfb77ddf06153c38953c'
assert sha(wrapper) == 'c42ff3744daacbc981becaf4bbcfd3861a68c76242469960d87085bd29d5a6d6'
newcode = CODE / 'research_live_obligation_initial_methods.py'
newtest = ROOT / 'tests/test_g31_circulation_online_initial_methods.py'
assert sha(newcode) == '36f76d65454d794e9ae51b71a8cc06ec4a22c99593ce125eda83439eee795d38'
assert sha(newtest) == 'd5b8d96ccecba0efa5e3a84ccc447084b332feb8f971bff9e49f17dbe2683d07'
text = source.read_text(encoding='utf8')
for a,b in (
 ('run_live_obligation_online_retained_policy_pure', 'run_online_initial_methods_pure'),
 ('tests/test_g31_circulation_live_obligation_online_retained_policy.py', 'tests/test_g31_circulation_online_initial_methods.py'),
 ('scripts/experiments/g31_ics_circulation/live_obligation_online_retained_policy.py', 'scripts/experiments/g31_ics_circulation/research_live_obligation_initial_methods.py'),
 ('6b284683e77ca9a3121f8c02c8641cd000091ad7c815fb0b30391c091d66b462', sha(newcode)),
 ('42ac004798f9bbdb3cb776d8b7e5b0d1abd0dcc2dee1f1d948b2afc269e31055', sha(newtest)),
 ('g31.live_obligation.online_retained_policy.synthetic22.v1', 'g31.live_obligation.online_initial_methods.synthetic21.v1'),
 ('EXPECTED_TESTS = 22', 'EXPECTED_TESTS = 21'),
 ('retained_policy_pure:', 'online_initial_methods_pure:'),
 ('Only22 synthetic cases', 'Only21 synthetic cases'),
 ('standalone22 synthetic gate', 'standalone21 synthetic gate'),
 ('passed_synthetic22', 'passed_synthetic21')):
    text = replace(text,a,b)
text = replace(text, "journal.emit('synthetic22'", "journal.emit('synthetic21'", 2)
compile(text,'<online_gate_source>','exec')
target = CODE / 'run_online_initial_methods_pure.py'
create(target,text)
ps = wrapper.read_text(encoding='utf8')
changes = [
 ('run_live_obligation_online_retained_policy_pure', 'run_online_initial_methods_pure',2),
 ('scripts/experiments/g31_ics_circulation/live_obligation_online_retained_policy.py', 'scripts/experiments/g31_ics_circulation/research_live_obligation_initial_methods.py',1),
 ('tests/test_g31_circulation_live_obligation_online_retained_policy.py', 'tests/test_g31_circulation_online_initial_methods.py',1),
 ('6b284683e77ca9a3121f8c02c8641cd000091ad7c815fb0b30391c091d66b462',sha(newcode),1),
 ('42ac004798f9bbdb3cb776d8b7e5b0d1abd0dcc2dee1f1d948b2afc269e31055',sha(newtest),1),
 ('47866a2db3e838ca40fb9f53719d13a6b0c48ffe448cdfb77ddf06153c38953c',sha(target),1),
 ('g31.live_obligation.online_retained_policy.synthetic22_external.v1','g31.live_obligation.online_initial_methods.synthetic21_external.v1',1),
 ('expected_tests = 22','expected_tests = 21',1),
 ('synthetic retained-policy22','synthetic online-initial-methods21',1),
 ('lorp1','oimp1',3),
]
for a,b,n in changes: ps=replace(ps,a,b,n)
newwrapper = OUT / 'root_oimp1_pure_001.ps1'
create(newwrapper,ps)
print(json.dumps({'runner_sha256':sha(target),'wrapper_sha256':sha(newwrapper),'unexecuted':True}))
