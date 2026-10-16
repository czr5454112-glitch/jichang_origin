from pathlib import Path
HERE=Path(__file__).resolve().parent
text=(HERE/'review_bdb1_prelaunch_001.py').read_text(encoding='utf8')
replacements={
 'outputs/bdb1':'outputs/bdb2','invoke_bdb1_prepare.ps1':'invoke_bdb2_prepare.ps1',
 '3332dbaac1422a0f7285db9d635b7efea4ecfdac859bb631a57867776c0f1c20':'2c2dc98fd018b8bb454847f5af67864d3012ae0e752df858fbc62ad2b4ed0ed7',
 '394d4a3a3c5dabded60d319223b38394e89c60666b39678c6849c8ed34d43642':'e306a3e21cf49d9abc4d5ab9fbfddf249afcbad2438ba31592dc8e4cbb152e95',
 'aeadc41cddf7f2becc06ac1626b8fc6a9ae622f8d083406cc7235c0b2ab55657':'6769e861068a6f171d9beadb91580cc10a41c50c6cdca59a8096e0a3afc5732c',
 '0b2c5569ae13aeff238bc25ce4ca4728a03a635d86c7078e5b8ef21f7e4b7a0e':'728e8b5ed9c2d1cb78b87ca3f03ab6aebc9d29c4f3709668d62a73ed13ae482a',
 '1cd691fd3345af90fc0a1b60005adc180d785eb00c959544dfa5ba4a3006b861':'a25788096882f4ad0ccf19d70df2f1156265e473a8bb8288be9ddbb2a05dff42',
 "module='scripts.experiments.g31_ics_circulation.diagnose_bound_source_proof_bind'":"module='scripts.experiments.g31_ics_circulation.diagnose_bound_source_proof_bind_v2'",
 'g31.bound_source_proof.one_bind_one_use.v1':'g31.bound_source_proof.one_bind_one_use.v2',
 'g31.bound_source_proof.prepare_external.v1':'g31.bound_source_proof.prepare_external.v2',
 "len(p['source_sha256'])==202":"len(p['source_sha256'])==209",
 "len(p['evidence_sha256'])==22":"len(p['evidence_sha256'])==461",
 "'sources':202":"'sources':209","'evidence':22":"'evidence':461",
}
for before,after in replacements.items():
    assert before in text,before
    text=text.replace(before,after)
needle="record={'schema':"
addition="""require(sha(ROOT/'outputs/bdbv2p1/root_saved_review_001.json')=='e8a65188f8c104d317b5b5f631b4e7f0b083479768c5d714d087753356045941','root8')
wiring=p['required_wiring_pure']
require(wiring['expected_tests']==8 and wiring['output_directory']==str(ROOT/'outputs/bdbv2p1'),'mandatory8')
for item in (*wiring['artifacts'].values(),wiring['wrapper']):
    require(sha(item['path'])==item['sha256']==p['evidence_sha256'][item['path']],'required8_provenance')
require(p['candidate_integration_source_proof']['inverse_worker_AST'] is True
    and p['candidate_integration_source_proof']['whole_owned_parent_and_main_unchanged'] is True
    and p['binder_v2_source_proof']['schema']=='g31.request_owned_bound_future_fork.v2','candidate_v2')
for item in p['failed_v1_preserved'].values():require(sha(item['path'])==item['sha256'],'failed_v1_stays')
"""
assert text.count(needle)==1;text=text.replace(needle,addition+needle)
with (HERE/'review_bdb2_prelaunch_001.py').open('x',encoding='utf8') as f:f.write(text)
