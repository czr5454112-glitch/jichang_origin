import json,sys,torch,pytest
from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3_bound as bound
from pathlib import Path
print(json.dumps({'torch_classes_type':str(type(torch.classes)),'class_file':vars(type(torch.classes)).get('__file__'),'instance_file':vars(torch.classes).get('__file__'),'getattr_file':getattr(torch.classes,'__file__',None),'phantom_in_closure':Path('_classes.py').resolve() in bound.imported_sources()}),flush=True)
raise SystemExit(pytest.main(sys.argv[1:]))
