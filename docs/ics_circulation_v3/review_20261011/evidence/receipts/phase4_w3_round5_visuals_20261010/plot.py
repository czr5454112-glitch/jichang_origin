"""Static, full-denominator development comparison from frozen result rows."""
from pathlib import Path
from hashlib import sha256
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).parent
SOURCE = OUT.parent / 'phase4_w3_empty_improvement_20261010/summary.json'
before = sha256(SOURCE.read_bytes()).hexdigest()
data = json.loads(SOURCE.read_text())
assert len(data['rows']) == 252 and data['statuses'] == {'controller_quiescent': 252}
policies = ['greedy', 'legacy_empty12', 'public_fast4', 'empty2_h40', 'empty12_h40', 'empty24_h40', 'empty24_h80']
labels = ['Greedy', 'Legacy empty 12', 'Public fast 4', 'New 2 / H40', 'New 12 / H40', 'New 24 / H40', 'New 24 / H80']
units = sorted({(r['scene'], r['tape']) for r in data['rows']})
lookup = {(r['scene'], r['tape'], r['policy']): r for r in data['rows']}
values = np.array([[lookup[s,t,p]['final']['total_cost'] - lookup[s,t,'greedy']['final']['total_cost']
                    for p in policies[1:]] for s,t in units])
fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 12), gridspec_kw={'width_ratios': [1.2, 1]}, layout='constrained')
bound = np.max(np.abs(values))
im = ax.imshow(values, cmap='RdBu_r', vmin=-bound, vmax=bound, aspect='auto')
ax.set_xticks(range(6), labels[1:], rotation=45, ha='right')
ax.set_yticks(range(36), [s.removeprefix('stream_') + ' / ' + t for s,t in units], fontsize=8)
for i in range(36):
    for j in range(6):
        ax.text(j, i, f'{values[i,j]:+.1f}' if values[i,j] else '0', ha='center', va='center', fontsize=7,
                color='white' if abs(values[i,j]) > bound*.65 else '#202020')
for y in (8.5,17.5,26.5):
    ax.axhline(y, color='black', lw=.8)
ax.set_title('All 36 paired task tapes\nFinal J minus greedy (lower is better)', fontsize=12)
fig.colorbar(im, ax=ax, shrink=.5, label='Paired cost difference')
colors = ['#6a6a6a','#007f6d','#4357ad','#b17618','#d34e36','#ba375e','#7d4389']
totals = []
offsets = [(10,10),(10,-14),(10,8),(10,8),(-20,-25),(10,10),(-10,12)]
for p, label, color, offset in zip(policies, labels, colors, offsets):
    rows = [r for r in data['rows'] if r['policy'] == p]
    cost = sum(r['final']['total_cost'] for r in rows)
    cpu = sum(r['invocation_cpu_seconds'] for r in rows)
    ontime = sum(r['final']['on_time'] for r in rows)
    totals.append({'policy': p, 'J': cost, 'CPU_seconds_including_case_setup_and_serialization': cpu, 'on_time': ontime})
    bx.scatter(cpu,cost,c=color,s=70,edgecolors='white',linewidth=.8,zorder=3)
    bx.annotate(label, (cpu,cost), xytext=offset, textcoords='offset points', fontsize=9,
                ha='right' if offset[0]<0 else 'left')
bx.set_xlim(0, max(t['CPU_seconds_including_case_setup_and_serialization'] for t in totals)*1.2)
bx.set_ylim(335, 590)
bx.set_xlabel('Total case invocation CPU seconds')
bx.set_ylabel('Total final cost J across 36 tapes')
bx.set_title('Cost vs. actual compute\n198 / 198 tasks completed by every policy', fontsize=12)
bx.grid(alpha=.22)
bx.text(.02,.48,'Legacy reference remains stronger.\nLarger new-method budgets have no benefit\non this reused development family.\n\nCPU is shared-machine process time;\nnot a hard real-time guarantee.',transform=bx.transAxes,fontsize=10,
        va='top',bbox=dict(facecolor='white',edgecolor='#dddddd',boxstyle='round,pad=.6'))
fig.suptitle('Direct empty-tray control: full development comparison', fontsize=16)
fig.savefig(OUT/'empty_control_comparison.png',dpi=170)
fig.savefig(OUT/'empty_control_comparison.svg')
assert sha256(SOURCE.read_bytes()).hexdigest() == before
manifest = {'source_sha256': before, 'source': str(SOURCE.resolve()), 'totals': totals,
    'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
    'outputs': {p.name: sha256(p.read_bytes()).hexdigest() for p in OUT.glob('empty_control_comparison.*')}}
with (OUT/'manifest.json').open('x',encoding='utf-8') as f:
    json.dump(manifest,f,indent=2)
