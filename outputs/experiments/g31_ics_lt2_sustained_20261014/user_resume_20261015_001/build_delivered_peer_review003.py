from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;OUT=HERE.parent
body=(HERE/'review_delivered_peer_root_002.py').read_text(encoding='utf8')
for old,new in [
 ('delivered_peer_cost_prepare_003','delivered_peer_cost_prepare_004'),
 ('153edb3418ff41beebba0c2f454280bd6dd2b854b7335142c9c9d2db5798b5ca','904afc076ef0d94d5a55356715473cedf9469715358debb473b2721b64e4cd62'),
 ("len(plan['sources'])==76","len(plan['sources'])==78"),("'source_count':76","'source_count':78"),
 ('All76source','All78source'),('measure_delivered_peer_cost_v3 --execute','measure_delivered_peer_cost_v4 --execute'),
 ('invoke_delivered_peer_root_002_measured.ps1','invoke_delivered_peer_root_003_measured.ps1'),
 ('external_wall.v3','external_wall.v4'),('root_review.v3','root_review.v4'),
 ("len(xml.findall('.//testcase'))==52","len(xml.findall('.//testcase'))==57"),("'pure_tests':52","'pure_tests':57"),
 ('v1/v2 frozen plans and failed root review retained.','v1/v2 frozen plans and failed root review retained. V3 actual failed before child launch because preparation stdout.log already existed;0validatorcalls. V4 gives each prepare/pure/execute stage distinct exclusive logs, five additional fake stage-flow tests,57pure passed. Full original checker/worker and source pins unchanged; prior failed003 and all earlier files retained.')]:
    assert old in body,old;body=body.replace(old,new)
with (HERE/'review_delivered_peer_root_003.py').open('x',encoding='utf8') as f:f.write(body)
path=OUT/'delivered_peer_cost_prepare_003/external_application_wall.json'
assert hashlib.sha256(path.read_bytes()).hexdigest()=='59d0d86c7a810f592977f807f299632b5e824c9c90661644b37b716647519d0f'
with (HERE/'delivered_peer_launch_failure_003.json').open('x',encoding='utf8') as f:json.dump({
 'status':'failed_before_worker_launch','outer_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'whole_python_seconds':0.4923005,'actual_validator_calls':0,'actual_digest_calls':0,
 'cause':'run_child used stdout.log for both prepare and execute; exclusive xb failed before bounded process creation.',
 'resolution':'New v4 per-stage exclusive log names and fake prepare-then-execute test; old003 retained. Fresh57pure004 and prepare004, no retry of003.'},f,indent=2)
