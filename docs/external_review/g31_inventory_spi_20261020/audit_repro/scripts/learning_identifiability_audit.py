"""Read-only audit of saved paired features and weights; requires NumPy.

Usage: python learning_identifiability_audit.py --root FIXED_CHECKOUT --output audit.json
No fit function or native executable is called. The row-space projection is
only a linear-algebra diagnostic and is not a new policy experiment.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=HERE.parent/'review_1d895da0_20261020')
parser.add_argument('--output',type=Path,default=HERE/'learning_identifiability_audit.json')
args=parser.parse_args()
ROOT=args.root.resolve()
CYCLE=ROOT/'outputs/experiments/g31_ics_action_value_20261020/cycle_001'

def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def bound_path(reference):
    relative=reference['path'].replace('\\','/').split('/outputs/',1)[1]
    path=ROOT/'outputs'/relative
    assert hashlib.sha256(path.read_bytes()).hexdigest()==reference['sha256']
    return path

def difference(vectors,names,scale):
    return (np.array([vectors[1][n] for n in names])-np.array([vectors[0][n] for n in names]))/scale

freeze=read(CYCLE/'all_models_frozen_001.json')
for frozen in freeze['models']:
    model=read(bound_path(frozen['checkpoint']))
    for relative,expected in model['registration']['feature_source_sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,relative
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
last=json.loads(gzip.decompress((CYCLE/'report_support/G_N26_C11_S29_P902_001_initial_241_callback_prefix_001.jsonl.gz').read_bytes()).splitlines()[-1])
callback=last['record']
assert ranker.digest(callback)==last['record_sha256']
first_rows=[dict(row,observation=callback['observation'],opportunity=callback['opportunity'],
    baseline_decision=callback['baseline_decision'],parent=callback['inference_parent'],
    forecast_evidence=callback['forecast_evidence']) for row in callback['inference_rows']]
out={'scope':'saved-data recomputation only; no retraining or native runs; projection is a diagnostic, not a newly evaluated policy',
     'fixed_commit':'1d895da00644c9486568fe74b835e057aa93f8c8','fit_calls':0,'native_jobs':0,
     'source_pins':ranker.source_pins(),'linear_models':[],'datasets':[],'first_G26_callback':{
     'sequence':callback['audit_sequence'],'physical_time':callback['observed_at'],
     'record_sha256':last['record_sha256'],'online_advantage':callback['predicted_patch_advantage'],
     'reference_action':first_rows[0]['semantic_action'],'patch_action':first_rows[1]['semantic_action']}}

datasets={}
for domain,folder in [('primary_22','training_primary_001'),('mixed_18_22_26','training_resource_001')]:
    train,dev=(read(CYCLE/folder/(split+'_datasets.json.gz')) for split in ('train','dev'))
    datasets[domain]=(train,dev)
    out['datasets'].append({'domain':domain,'train_pairs':len(train),'dev_pairs':len(dev),
        'train_rows':[{'pair_id':x['pair']['pair_id'],'parent_group':x['pair']['parent']['parent_group'],
          'fleet':x['pair']['parent']['fleet'],'time':x['pair']['reference_cost']['label_start'],
          'advantage':x['pair']['advantage_bag_seconds'],'owner':x['rows'][0]['observation']['owner_id'],
          'reference':x['rows'][0]['semantic_action'],'patch':x['rows'][1]['semantic_action'],
          'complete_prefix_sha256':x['pair']['complete_prefix_sha256']} for x in train]})

for frozen in freeze['models']:
    if frozen['checkpoint']['architecture']!='linear':
        continue
    model_path=bound_path(frozen['checkpoint']);model=read(model_path)
    assert model['registration']['feature_source_sha256']==ranker.source_pins()
    train,dev=datasets[frozen['training_domain']]
    assert ranker.digest(train)==model['training_dataset_sha256']
    pairs,_=ranker.prepare_pairs(train,information_variant=model['information_variant'],split='train')
    devpairs,_=ranker.prepare_pairs(dev,information_variant=model['information_variant'],split='dev')
    names=model['feature_names'];p=model['parameters'];scale=np.array(p['scale']);target_scale=p['target_scale']
    X=np.array([difference((x['reference'],x['patch']),names,scale) for x in pairs])
    u,s,vh=np.linalg.svd(X,full_matrices=False)
    tolerance=np.finfo(float).eps*max(X.shape)*s[0]
    rank=int(np.sum(s>tolerance));basis=vh[:rank]
    w=np.array(p['layers'][0]['weight'][0]);wp=basis.T@(basis@w);wn=w-wp
    predict=ranker.prepare_predictor(model)
    def row_report(reference,patch,actual=None):
        vectors=ranker._pair_features(reference,patch,model['information_variant'])
        d=difference(vectors,names,scale);dp=basis.T@(basis@d);dn=d-dp
        full=float(d@w*target_scale);supported=float(d@wp*target_scale)
        assert abs(full-predict(reference,patch))<1e-6
        return {'observed_at':reference['observation']['now'],'owner':reference['observation']['owner_id'],
          'actual_advantage':actual,'full_prediction':full,'row_space_weight_prediction':supported,
          'null_space_weight_prediction':full-supported,
          'out_of_row_space_norm_fraction':float(np.linalg.norm(dn)/max(np.linalg.norm(d),1e-15)),
          'action_would_change_after_projection':(full>0)!=(supported>0)},d,dn
    dev_rows=[row_report(x['raw']['rows'][0],x['raw']['rows'][1],x['advantage'])[0] for x in devpairs]
    first,d,dn=row_report(*first_rows)
    alt=w-2*(d@w)/(dn@dn)*dn
    max_train_change=float(np.max(np.abs(X@(alt-w)))*target_scale)
    result={'domain':frozen['training_domain'],'variant':model['information_variant'],'seed':model['seed'],
        'model_id':model['model_id'],'model_path':str(model_path.relative_to(ROOT)),
        'feature_dimension':len(names),'training_pair_count':len(pairs),'matrix_rank':rank,
        'singular_values':s.tolist(),'rank_tolerance':float(tolerance),'nullity':len(names)-rank,
        'zero_difference_features':[name for name,column in zip(names,X.T) if np.max(np.abs(column))<1e-12],
        'null_space_weight_norm_fraction':float(np.linalg.norm(wn)/np.linalg.norm(w)),
        'max_training_prediction_change_after_weight_projection':float(np.max(np.abs(X@(wp-w)))*target_scale),
        'dev_projection_diagnostics':dev_rows,'first_G26_7200_diagnostic':first,
        'first_G26_same_training_predictions_opposite_action_counterexample':{
            'original_prediction':float(d@w*target_scale),'alternative_prediction':float(d@alt*target_scale),
            'max_change_in_all_train_predictions':max_train_change,
            'weight_change_norm':float(np.linalg.norm(alt-w)),
            'scope':'data-term identifiability only; regularization penalties may differ; no alternative model has been trained or deployed'}}
    out['linear_models'].append(result)

target=args.output.resolve()
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
for x in out['linear_models']:
    z=x['first_G26_7200_diagnostic']
    print(x['domain'],x['variant'],x['seed'],'rank',x['matrix_rank'],'/',x['feature_dimension'],
          'nullw',round(x['null_space_weight_norm_fraction'],4),'G26 full/span/null',
          [round(z[k],6) for k in ('full_prediction','row_space_weight_prediction','null_space_weight_prediction')],
          'OOD',round(z['out_of_row_space_norm_fraction'],4),
          'train_projection_change',x['max_training_prediction_change_after_weight_projection'])
print(target)
