from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
body=(HERE/'review_delivered_peer_root_001.py').read_text(encoding='utf8')
for old,new in [
 ('delivered_peer_cost_prepare_002','delivered_peer_cost_prepare_003'),
 ('961636f1aad6681d968ddfaa4667c0e27e6d385ab8aea53c95fc37d63338ac90','153edb3418ff41beebba0c2f454280bd6dd2b854b7335142c9c9d2db5798b5ca'),
 ("len(plan['sources'])==75","len(plan['sources'])==76"),
 ("'source_count':75","'source_count':76"),
 ('All75source','All76source'),
 ('measure_delivered_peer_cost_v2 --execute','measure_delivered_peer_cost_v3 --execute'),
 ('invoke_delivered_peer_root_001_measured.ps1','invoke_delivered_peer_root_002_measured.ps1'),
 ('g31.delivered_peer_actual32.external_wall.v2','g31.delivered_peer_actual32.external_wall.v3'),
 ('g31.delivered_peer_actual32.root_review.v2','g31.delivered_peer_actual32.root_review.v3'),
 ('Private prepare/execute/saved audit allboundnewchecker.','Private prepare/execute/saved audit allboundnewchecker. Root first prelaunch source-count check then found bare reused test import absent from v2 archive; no actual run. V3 explicitly includes that source, re-passed all52 tests,76 sources; v1/v2 frozen plans and failed root review retained.')]:
    assert old in body,old
    body=body.replace(old,new)
with (HERE/'review_delivered_peer_root_002.py').open('x',encoding='utf8') as f:f.write(body)
with (HERE/'delivered_peer_prelaunch_failure_001.json').open('x',encoding='utf8') as f:json.dump({
 'status':'prelaunch_source_domain_check_failed_before_actual',
 'failed_script':'review_delivered_peer_root_001.py','actual_validator_calls':0,
 'cause':'Expected75 files but found74; source_closure did not resolve bare import of original harness tests from tests search path.',
 'preserved':['delivered_peer_cost_pure_001','delivered_peer_cost_prepare_001','delivered_peer_cost_pure_002','delivered_peer_cost_prepare_002'],
 'resolution':'New v3 explicitly adds original harness test entry; new52pure003 and prepare003. No old source/receipt overwritten.'},f,indent=2)
