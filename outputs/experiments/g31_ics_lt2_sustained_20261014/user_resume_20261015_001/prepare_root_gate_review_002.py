"""Generate a new root-review file; never alter withheld version001."""
from pathlib import Path
here=Path(__file__).resolve().parent
text=(here/'review_initial_owner_gate_001.py').read_text(encoding='utf8')
changes={
 'initial_owner_route_gate_campaign as c':'initial_owner_route_gate_campaign_v2 as c',
 'launch_initial_owner_route_gate_campaign as launcher':'launch_initial_owner_route_gate_campaign_v2 as launcher',
 'verify_initial_owner_route_gate_campaign as verifier':'verify_initial_owner_route_gate_campaign_v2 as verifier',
 "out=c.OUT/'initial_owner_route_gate_campaign_prepare_001'":"out=c.OUT/'initial_owner_route_gate_campaign_prepare_002'",
 '8511a7554b4a365d8ef276a5972ecd77b033ab3db11dbaf1a7e71a3860dbc7ec':'659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4',
 "len(plan['source_sha256'])==139":"len(plan['source_sha256'])==141",
 'dict(tests=113,failures=0,errors=0,skipped=0)':'dict(tests=130,failures=0,errors=0,skipped=0)',
 'e1e67f504c47439b819515b355ecbe3e69cc908d76e2843ae4e3791653078ef5':'1f682f58d7a612aea72d12fbbe351c3254164ac70cbf199898750cd0011ba708',
 'invoke_initial_owner_gate_001_measured.ps1':'invoke_initial_owner_gate_002_measured.ps1',
 "'initial_owner_route_campaign_v3_prepare_001':'initial_owner_route_gate_campaign_prepare_001'":"'initial_owner_route_campaign_v3_prepare_001':'initial_owner_route_gate_campaign_prepare_002'",
 "'launch_initial_owner_route_campaign_v3':'launch_initial_owner_route_gate_campaign'":"'launch_initial_owner_route_campaign_v3':'launch_initial_owner_route_gate_campaign_v2'",
 "'live_archive_sources_verified':139":"'live_archive_sources_verified':141",
 'ACK change expression evaluated once; original row ACK assignment is unconditional. Repeated fresh equal ACK objects keep actual query calls while storing one complete body. Empty resets and retry terminal resets retain original behavior.':'Original ACK-change expression evaluated once and unconditional row assignment retained. Separate strict body_is_new checks dictionary order, builtin type, finite float.hex and signed zero. Equal Python ACKs with a different representation get a new full body even when ack_changed stays false. Actual queries, empty resets and retry terminal resets remain unchanged.',
 'Complete compiled scheduler synthetic differential and adversarial corrupted projection tests passed; real v3 ACK shapes only used for shape testing, not future information for policy.':'Compiled scheduler differential and all original gates retained. New intermediate equal-but-reordered and int/float/signed-zero changes followed by final restoration are checked per query. Tests reproduce the withheld001 gap without changing its139-source package. Actual v3 ACK shapes are shape data, not future policy information.',
}
for before,after in changes.items():
    assert before in text,before
    text=text.replace(before,after)
marker="assert plan['rows']==previous['rows']"
addition="""
withheld=c.OUT/'initial_owner_route_gate_campaign_prepare_001'
assert c.sha(withheld/'root_dispatch_withheld_001.json')=='9b0a188713e33412b13990e3393377e147825e6fd3528a60bc333c55d699f759'
old_gate=c.read(withheld/'campaign.json');assert len(old_gate['source_sha256'])==139
for name,digest in old_gate['source_sha256'].items():
    assert c.sha(name)==c.sha(withheld/old_gate['source_archive'][name])==digest
assert not (withheld/'execution_claim.json').exists()
"""
assert marker in text;text=text.replace(marker,marker+addition)
with (here/'review_initial_owner_gate_002.py').open('x',encoding='utf8') as f:f.write(text)
