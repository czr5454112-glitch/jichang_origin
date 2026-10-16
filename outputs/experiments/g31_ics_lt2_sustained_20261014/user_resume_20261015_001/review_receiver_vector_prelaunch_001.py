"""Root checks prepared vector ABBA without constructing a context."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_preference_receiver_vector_context as m

D = m.OUT / 'preference_receiver_vector_pair_001'
ready = json.loads((D / 'ready.json').read_bytes())
assert m.sha(D / 'ready.json') == '958ebb63d4ceaa0d5e8b2fd97e4e969e0f2266f0d6ec282b7c1de482587bbbb7'
assert m.sha(D / 'preregistered_protocol.json') == ready['plan_sha256'] == '80f713be813bf769a6f190518b1a9dc1c5ae7c55750b1ff979f92fac9e2629da'
plan = json.loads((D / 'preregistered_protocol.json').read_bytes())
m.check_plan(plan)
# This reviewer is an extra loaded __main__, outside the executable harness.
# Compare that exact extra file separately, never ignore an arbitrary mismatch.
inventory = m.inventory()
reviewer_key = str(Path(__file__).resolve().relative_to(m.ROOT))
assert inventory.pop(reviewer_key) == m.sha(__file__)
assert inventory == plan['source_sha256']
for name, digest in inventory.items():
    assert m.sha(m.ROOT / name) == m.sha(D / 'source' / name) == digest
for name, digest in plan['pure_gate'].items():
    assert m.sha(name) == digest
assert m.oracle_pins() == plan['independent_accepted_oracle']['sha256']
assert m.sha(plan['input']['path']) == m.INPUT_SHA
selected = [r for r in json.loads(Path(plan['input']['path']).read_bytes()) if r['owner'] == 'A']
assert [r['case'] for r in selected] == list(m.CASES)
for row, source in zip(plan['cases'], selected, strict=True):
    assert m.sha(D / row['input']) == row['input_sha256']
    assert m.encoded(json.loads((D / row['input']).read_bytes())) == m.encoded(source['bundle'])
assert len(plan['source_sha256']) == ready['source_count'] == 45
assert m.sha(Path(ready['wrapper'])) == ready['wrapper_sha256'] == '85bc8257a8fb263845fdff1e95bbfeec9cad7f3b3900411ebdbc87e65e7fc287'
assert m.sha(D / 'vector_proof.json') == ready['proof_sha256']
xml_path = next(Path(p) for p in plan['pure_gate'] if p.endswith('tests.xml'))
cases = ET.parse(xml_path).getroot().findall('.//testcase')
assert len(cases) == ready['pure_tests'] == 56
assert not any(c.tag in ('skipped', 'failure', 'error') for t in cases for c in t)
assert m.sha(xml_path) == ready['pure_tests_sha256']
assert not any((D / n).exists() for n in ('execution_claim.json', 'ledger.json', 'receipt.json', 'external_application_wall.json'))
report = {'status': 'passed_source_and_prepared_bindings_no_execution', 'plan_sha256': ready['plan_sha256'],
          'sources': 45, 'pure_tests': 56, 'wrapper_sha256': ready['wrapper_sha256'], 'native_calls': 0,
          'projection_calls': 0, 'complete_100ms_certified': False,
          'review_precheck_correction': 'The first review imported the dynamic inventory checker from an extra root __main__, so it stopped before any result or execution. This reviewer now removes only its own explicitly hashed file and checks the exact45 campaign files, archives, inputs and pure gates. The actual launcher keeps the original inventory guard unchanged.',
          'checks': ['Root read full candidate, timing harness, parity/AST/isolation tests and external wrapper.',
                     'All immutable five times originate in this request actual validated full baseline; no stored external outcomes used by context.',
                     'Only baseline completion extraction changes; full and partial outputs must match frozen accepted oracle and fresh A.',
                     'Full source checks, constructor, baseline, all32 candidates and encoding are inside each batch.',
                     'All24 ABBA batches, raw outputs, independent readback and source verification charged to120s Job and external whole Python wall.']}
path = D / 'root_prelaunch_review_001.json'
with path.open('x', encoding='utf8') as f:
    json.dump(report, f, indent=2)
print(json.dumps({'status': report['status'], 'sha256': m.sha(path)}))
