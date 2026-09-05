"""Summarize every completed map2 hypothesis without selecting a G31-favorable row."""
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'outputs/runtime/feng_dh_semantics_reaudit_20260905'
HISTORY = ROOT / 'outputs/runtime/feng_dh_historical_signatures_20260905/paired_segments.csv.gz'
TABLE = ROOT / 'outputs/tables/feng_dh_semantics_reaudit_20260905.csv'
FIGURE = ROOT / 'outputs/figures/feng_dh_semantics_reaudit_20260905.png'


def stats(values):
    values = sorted(values)
    def q(p):
        x = (len(values)-1)*p; i = int(x)
        return values[i] + (values[min(i+1,len(values)-1)]-values[i])*(x-i)
    return dict(min=values[0], mean=sum(values)/len(values), p95=q(.95), p99=q(.99), max=values[-1])


def main():
    historical = defaultdict(float)
    historical_od = defaultdict(list)
    with gzip.open(HISTORY, 'rt', encoding='utf-8') as f:
        paired = list(csv.DictReader(f))
    for row in paired:
        value = float(row['historical_dh_seconds'])
        historical[int(row['raw_bag_id'])] += value
        historical_od[(row['start'], row['goal'])].append(value)
    assert len(historical) == 28506 and len(paired) == 43603
    reference = stats(historical.values())
    results = [dict(run='historical_workbook', raw_bags=28506, segments=43603, **reference,
                    mean_relative_error=0, max_relative_error=0, protocol='historical_observation')]
    distributions = {'historical_workbook': list(historical.values())}
    od_rows = []
    for path in sorted(RUNTIME.glob('*/population_and_gate.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        identity = json.loads((path.parent/'run_identity.json').read_text(encoding='utf-8'))
        if identity['status'] != 'COMPLETE' or not all(data['checks'].values()):
            raise RuntimeError(f'incomplete or invalid run {path.parent}')
        for filename in ('bags.csv.gz', 'segments.csv.gz'):
            archive = path.parent/filename
            if hashlib.sha256(archive.read_bytes()).hexdigest() != identity['outputs'][filename]:
                raise RuntimeError(f'archive identity mismatch {archive}')
        with gzip.open(path.parent/'bags.csv.gz', 'rt', encoding='utf-8') as f:
            values = [float(r['table53_scheduled_interval_seconds']) for r in csv.DictReader(f)]
        observed = stats(values)
        assert len(values) == 28506
        for key in reference:
            assert abs(observed[key] - data['THT_seconds_shared_D'][key]) < 1e-6
        results.append(dict(run=path.parent.name, raw_bags=len(values), segments=data['completed_segments'],
                            **observed, mean_relative_error=observed['mean']/reference['mean']-1,
                            max_relative_error=observed['max']/reference['max']-1,
                            protocol=identity.get('protocol_path', 'initial_map2_protocol')))
        distributions[path.parent.name] = values
        with gzip.open(path.parent/'segments.csv.gz', 'rt', encoding='utf-8') as f:
            grouped = defaultdict(list)
            for row in csv.DictReader(f):
                grouped[(row['start'],row['goal'])].append(float(row['table53_scheduled_interval_seconds']))
        for od, times in grouped.items():
            actual, expected = stats(times), stats(historical_od[od])
            od_rows.append(dict(run=path.parent.name,start=od[0],goal=od[1],count=len(times),
                                mean_seconds=actual['mean'],historical_mean_seconds=expected['mean'],
                                mean_relative_error=actual['mean']/expected['mean']-1,
                                min_seconds=actual['min'],historical_min_seconds=expected['min'],
                                max_seconds=actual['max'],historical_max_seconds=expected['max']))
    TABLE.parent.mkdir(exist_ok=True,parents=True)
    with TABLE.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    with TABLE.with_name(TABLE.stem+'_by_od.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(od_rows[0]));writer.writeheader();writer.writerows(od_rows)
    labels = {
        'historical_workbook': 'Historical DH',
        'repaired_control': 'Control',
        'retained_boundary_v2': 'V2: full upstream retention',
        'retained_boundary_v2_id_order': 'V2 + ID order',
        'overlap_id_order': 'Control + ID order',
        'outlet_gate_v3_snapshot': 'V3: frozen outlet gate',
        'next_tick_service_v4': 'V4: next-tick node service',
        'boundary_clearance_v5': 'V5: body clearance',
        'post_movement_scoring_v6': 'V6: post-movement scoring',
    }
    fig,axes=plt.subplots(1,2,figsize=(13.5,5.4))
    for label,values in distributions.items():
        if label == 'outlet_gate_v3': continue  # Identical map2 distribution to its snapshot correction.
        ordered=sorted(values);y=[(i+1)/len(ordered) for i in range(len(ordered))]
        axes[0].plot(ordered,y,label=labels.get(label,label),linewidth=2 if label=='historical_workbook' else 1.2)
    axes[0].set_xscale('log');axes[0].set_xlabel('Per-bag THT, shared-D (s), log scale')
    axes[0].set_ylabel('Completed population fraction');axes[0].grid(alpha=.2)
    axes[0].legend(loc='lower right',fontsize=7,framealpha=.9)
    selected=[r for r in results if r['run']!='outlet_gate_v3']
    y=list(range(len(selected)))
    axes[1].barh(y,[r['mean'] for r in selected],color=['#222222' if r['run']=='historical_workbook' else '#497bb4' for r in selected])
    axes[1].set_yticks(y,[labels.get(r['run'],r['run']) for r in selected],fontsize=8);axes[1].invert_yaxis()
    for i,r in enumerate(selected):
        axes[1].text(r['mean']+8,i,f"{r['mean']:.2f}",va='center',fontsize=8)
    axes[1].set_xlim(0,max(r['mean'] for r in selected)*1.14)
    axes[1].set_xlabel('Mean THT (s)');axes[1].grid(axis='x',alpha=.2)
    fig.suptitle('Feng map2 semantic hypotheses: all 28,506 bags / 43,603 legs')
    fig.tight_layout(); FIGURE.parent.mkdir(exist_ok=True,parents=True);fig.savefig(FIGURE,dpi=180);plt.close(fig)
    summary={'reference_seconds':reference,'runs':results,'new_extension_runs_in_this_reaudit_root':0,
             'scope':'Map2 semantic re-audit; the later user-selected V5 campaign is separate.',
             'acceptance_policy':'User accepts close or moderately slower; old numerical thresholds are diagnostic only.'}
    (RUNTIME/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))


if __name__ == '__main__':
    main()
