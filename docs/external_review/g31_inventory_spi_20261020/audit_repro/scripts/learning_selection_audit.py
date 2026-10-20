"""Recompute saved dev scores and checkpoint choices; requires NumPy.

Usage: python learning_selection_audit.py --root FIXED_CHECKOUT --output audit.json
Only saved feature extraction, saved-weight inference and selection are run.
No training, native executable or modified policy is evaluated.
"""
from pathlib import Path
import gzip,hashlib,json,sys,math,argparse
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=HERE.parent/'review_1d895da0_20261020')
parser.add_argument('--output',type=Path,default=HERE/'learning_selection_audit.json')
args=parser.parse_args()
ROOT=args.root.resolve()
CYCLE=ROOT/'outputs/experiments/g31_ics_action_value_20261020/cycle_001'

def read(path):
    raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
def bound(reference):
    path=ROOT/'outputs'/reference['path'].replace('\\','/').split('/outputs/',1)[1]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==reference['sha256']
    return path

def compare(left,right,errors):
    if type(left) in (int,float) and type(right) in (int,float):
        errors.append(abs(left-right))
        assert math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-7),(left,right)
    elif isinstance(left,dict):
        assert set(left)==set(right)
        for key in left:compare(left[key],right[key],errors)
    elif isinstance(left,list):
        assert len(left)==len(right)
        for a,b in zip(left,right):compare(a,b,errors)
    else:assert left==right,(left,right)

frozen=read(CYCLE/'all_models_frozen_001.json')
for x in frozen['models']:
    model=read(bound(x['checkpoint']))
    for relative,expected in model['registration']['feature_source_sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,relative
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
out={'fit_calls':0,'native_jobs':0,'scope':'recompute dev weights, features, selection and baselines from saved artifacts','chains':[]}
for x in frozen['models']:
    selected_path=bound(x['checkpoint']);chain=selected_path.parent
    selection_path=bound(x['selection']);old=read(selection_path)
    folder='training_primary_001' if x['training_domain']=='primary_22' else 'training_resource_001'
    train,dev=(read(CYCLE/folder/(s+'_datasets.json.gz')) for s in ('train','dev'))
    models=[read(chain/(arch+'_model.json')) for arch in ('linear','small_mlp')]
    assert all(ranker.digest(train)==m['training_dataset_sha256'] for m in models)
    recomputed=ranker.select_on_dev(models,dev)
    assert recomputed['selected_model_id']==old['selected_model_id']==x['model_id']
    errors=[]
    compare(recomputed['development_results'],old['development_results'],errors)
    controls=read(CYCLE/folder/'controls.json')
    pairs,_=ranker.prepare_pairs(dev,information_variant=x['information_variant'],split='dev')
    ref_regret=sum(max(0,p['advantage']) for p in pairs)/len(pairs)
    ref_failures=sum(sum(not a['positive_delivered_ack'] for a in p['raw']['rows'][0]['actual_execution']['attempts']) for p in pairs)
    assert abs(ref_regret-controls['dev_mean_regret']['reference_rule'])<1e-8
    selected=next(r for r in recomputed['development_results'] if r['model_id']==x['model_id'])
    out['chains'].append({'domain':x['training_domain'],'variant':x['information_variant'],'seed':x['seed'],
       'model_id':x['model_id'],'architecture':x['checkpoint']['architecture'],
       'saved_selection_identity_recomputed_exactly':True,'max_numeric_recompute_error':max(errors,default=0),'dev_pair_count':len(pairs),
       'selected_regret':selected['mean_paired_regret'],'selected_known_harm':selected['selected_known_harmed_jobs'],
       'selected_ack_failure_count':selected['selected_failure_count'],
       'reference_regret':ref_regret,'reference_known_harm':0,'reference_ack_failure_count':ref_failures,
       'reference_wins_existing_lexicographic_objective':
           (ref_failures,0,ref_regret)<(selected['selected_failure_count'],selected['selected_known_harmed_jobs'],selected['mean_paired_regret']),
       'actual_nonzero_dev_labels':[p['advantage'] for p in pairs if p['advantage']!=0],
       'selected_nonzero_dev_rows':[r for r in selected['rows'] if r['actual_advantage']!=0]})

path=args.output.resolve();path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
for row in out['chains']:
    print(row['domain'],row['variant'],row['seed'],row['architecture'],'ref_wins',row['reference_wins_existing_lexicographic_objective'],
          'regret',round(row['selected_regret'],6),'reference',round(row['reference_regret'],6),'harm',row['selected_known_harm'])
print(path)
