"""Same fixed-six diagnostic, profiling the entire fresh scoped candidate call."""
import time
BOOT=time.monotonic()
import ast,copy,hashlib,inspect,textwrap
from pathlib import Path
from types import FunctionType
from . import profile_live_lazy_six as old
from . import public_live_obligation_scoped_inputs as candidate
from . import measure_scoped_public_inputs_six as cost
from . import initial_owner_route_image as image

ROOT,OUT,LIMIT=old.ROOT,old.OUT,old.LIMIT
MODULE='scripts.experiments.g31_ics_circulation.profile_scoped_public_inputs_six'
SCHEMA='g31.scoped_public_inputs_six.cProfile.v1'
BASE=OUT/'scoped_public_inputs_six_cost_prepare_001'
PURE=OUT/'scoped_profile_binding_pure_001'
TEST='tests/test_g31_circulation_scoped_profile_binding.py'


def private(function,changes):
    assert set(changes)<=set(function.__globals__)
    value=FunctionType(function.__code__,{**function.__globals__,**changes},function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value


def build_worker():
    tree=ast.parse(textwrap.dedent(inspect.getsource(old.worker)))
    original=copy.deepcopy(tree);nodes=[n for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)
        and n.level==1 and n.module is None and len(n.names)==1
        and n.names[0].name=='public_live_obligation_lazy_communication_projection' and n.names[0].asname=='lazy']
    assert len(nodes)==1
    nodes[0].names[0].name='public_live_obligation_scoped_inputs'
    restored=copy.deepcopy(tree)
    for n in ast.walk(restored):
        if isinstance(n,ast.ImportFrom) and len(n.names)==1 and n.names[0].name=='public_live_obligation_scoped_inputs':
            n.names[0].name='public_live_obligation_lazy_communication_projection'
    assert ast.dump(restored,include_attributes=False)==ast.dump(original,include_attributes=False)
    namespace={**old.worker.__globals__,'SCHEMA':SCHEMA}
    exec(compile(ast.fix_missing_locations(tree),'<scoped-profile-import-only>','exec'),namespace)
    return namespace['worker']


worker=build_worker()
execute=private(old.execute,{'MODULE':MODULE,'BOOT':BOOT})


def prepare(output):
    old.no_execution_extensions();cost.pure_guard()
    import xml.etree.ElementTree as ET
    receipt=old.read(PURE/'receipt.json');cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    assert receipt['status']=='passed' and len(cases)==4 and receipt['source_changed']==[]
    assert receipt['XML_sha256']==old.sha(PURE/'tests.xml')
    assert not any(c.tag in ('failure','error','skipped') for r in cases for c in r)
    for p,d in receipt['source_sha256'].items():assert old.sha(p)==d==old.sha(PURE/'source'/Path(p).relative_to(ROOT))
    assert old.sha(BASE/'plan.json')=='d4c69fe70c5c6bd567677f9a04c2b024b47f1a6e25a9e671a932ef8e938b6d04'
    assert old.sha(BASE/'report.json')=='f6c8c0ebda0a87d727196bd9afffda795b0267fd492a6e9679ea5a3204fd0f55'
    assert old.sha(OUT/'scoped_inputs_saved_review_prepare_001/report.json')=='02e5feaafbada1f2879518e7412bccbaddeb5a636f3d999d2c32785574ccfe52'
    previous=old.read(BASE/'plan.json');plan=copy.deepcopy(old.read(cost.PROFILE/'plan.json'))
    files=image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.'),
        'scripts.experiments.g31_ics_circulation.run_scoped_profile_binding_pure'))
    for p,d in previous['source_sha256'].items():
        assert old.sha(p)==d==old.sha(BASE/previous['source_archive'][p]);files[str(Path(p).relative_to(ROOT))]=Path(p).read_bytes()
    output.mkdir(exist_ok=False);pins={};archives={}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        pins[str(ROOT/name)]=hashlib.sha256(data).hexdigest();archives[str(ROOT/name)]=str(path.relative_to(output))
    evidence=dict(plan['evidence_sha256']);evidence.update(previous['evidence_sha256'])
    for p in (BASE/'plan.json',BASE/'report.json',BASE/'receipt.json',BASE/'external_application_wall.json',
        OUT/'scoped_inputs_saved_review_prepare_001/report.json',PURE/'receipt.json',PURE/'tests.xml'):
        evidence[str(p)]=old.sha(p)
    plan.update(schema=SCHEMA,source_sha256=pins,source_archive=archives,evidence_sha256=evidence,
        model_source=old.ref(candidate.__file__),source_proof=candidate.PublicInputScope().source_proof(),
        preparation_public_input_constructions=1,preparation_model_calls=0,
        changed_source='Exactly one worker model import. Original context/model profile boundaries, all target and output checks unchanged.',
        cleanup_limit='Fresh scope construction/binding inside callback; natural GC remains enabled, cycle cleanup may run later; whole includes process shutdown.')
    plan['phase_boundaries']['model_profile']='Entire candidate.predict(context,action), including one fresh public construction/private bindings, every unchanged guard/full model and return. Exactly six calls; profiler perturbation, no speed claim.'
    old.write(output/'plan.json',plan);old.write(output/'rows.json',plan['rows'])
    old.write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':old.ref(output/'plan.json'),
        'source_count':len(pins),'new_binding_pure_tests':4,'original_profile_pure_tests':12,
        'native_calls':0,'model_calls':0,'execute_command':['C:/PROGRAMING/python3.11.9/python.exe','-m',MODULE,
            '--execute','--output',str(output),'--expected-plan',old.sha(output/'plan.json')]})


main=private(old.main,{'worker':worker,'execute':execute,'prepare':prepare})
if __name__=='__main__':raise SystemExit(main())
