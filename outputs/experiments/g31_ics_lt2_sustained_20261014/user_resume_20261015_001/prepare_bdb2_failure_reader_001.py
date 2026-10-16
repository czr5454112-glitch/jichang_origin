"""Version exact saved-only bdb1 reader; no project imports or execution."""
from pathlib import Path
import hashlib

here = Path(__file__).resolve().parent
source = here / 'review_bdb1_failure_001.py'
text = source.read_text(encoding='utf8')
replacements = {
    "OUT=ROOT/'outputs/bdb1'": "OUT=ROOT/'outputs/bdb2'",
    'd4b74b873b652a5fcd487e2dc82161f31c862f192f2fd818e066f106cb4ab00d': '48a37a6e8ad0b17a0ec43e34ba04ff566100c51f3e3b152614f5c26e60e1f854',
    '67173f0acc53a00d043fe8eeccc51cf965d295d5d120299ce40e1932706a5076': '123317d561f9f0b72ceaef038d8ef249ac760f5aae9dde294e31210c34487934',
    '738f8ab582f7678aa304f8faceacf4c0ee0f3d07c8dfa0740d526fae7bc35b5c': 'fab293bc7de7c6155f68cf9a58ef4bb937f1af4dfcf9473ebd7baa38876bfbd7',
    '4c1739f822d59f2d739216edaad4d5c58d585b74c5fcb9b6221e501232016f46': '83fb0666946db0fe78163fba4ecc20b0013a642fae98b935356acad1f08ecbfb',
    '3332dbaac1422a0f7285db9d635b7efea4ecfdac859bb631a57867776c0f1c20': '2c2dc98fd018b8bb454847f5af67864d3012ae0e752df858fbc62ad2b4ed0ed7',
    "and 'bound_source_proof:nonfinite_static_value' in q['error']": "and 'bound_source_proof:unsupported_static_object' in q['error']\n    and 'dependency_label=root:original_proof:_source_inventory:core.build_parts:lazy.check_sources:previous.check_sources:original.annotations' in q['error']",
    "len(p['source_sha256'])==202 and len(p['evidence_sha256'])==22": "len(p['source_sha256'])==209 and len(p['evidence_sha256'])==461",
    "'source_count':202,'evidence_count':22": "'source_count':209,'evidence_count':461",
    'Dependency traversal rejected a nonfinite static float before original proof execution. Traceback did not identify the specific dependency label.': 'Dependency traversal rejected an unsupported static object at original.annotations before original proof execution. Full exact dependency label remains in the saved traceback. This attempt did not validate the complete dependency domain.',
    'Versioned exact IEEE float-bit binding including infinities/NaNs/signed zero; preserve model/JSON finite-input guards and full dependency coverage. Improve diagnostic labels. No repeat actual dispatch authorized by this record.': 'Versioned exact canonical __future__.annotations binding with full pinned standard-library class and instance integrity; preserve v2 static float codec, finite JSON and all dependency checks. No repeat dispatch authorized by this record.',
}
for old, new in replacements.items():
    assert text.count(old) == 1, old
    text = text.replace(old, new)
compile(text, '<bdb2_saved_reader>', 'exec')
target = here / 'review_bdb2_failure_001.py'
with target.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(text)
print(hashlib.sha256(target.read_bytes()).hexdigest())
