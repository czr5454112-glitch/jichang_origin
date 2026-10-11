"""All 27 cases; both timing repetitions shown, no significance claims."""
from pathlib import Path
from hashlib import sha256
import json,sys
from time import process_time,perf_counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

cpu,wall=process_time(),perf_counter()
source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
d=json.loads(source.read_text(encoding='utf8'));cases=d['cases']
fig,axes=plt.subplots(1,2,figsize=(14,12),sharey=True)
colors={'counterflow':'#1f77b4','cross_cycle':'#a14c86','near_full':'#298b66'}
for ax,key,title in zip(axes,('algorithm_cpu_seconds','process_cpu_seconds'),
                       ('Algorithm CPU: screen + search + dispatch','Complete child process CPU: Windows OS')):
    ax.axvline(0,color='#555555',linewidth=1)
    for i,c in enumerate(cases):
        scene=c['case_id'].split('__')[0];values=[r['on_minus_off'][key]for r in c['block_pair_deltas']]
        ax.plot([min(values),max(values)],[i,i],color=colors[scene],alpha=.5,linewidth=2)
        ax.scatter(values,[i,i],color=colors[scene],s=22,zorder=3)
        ax.scatter([c['on_minus_off_mean'][key]],[i],color=colors[scene],s=34,marker='D',zorder=4)
    ax.set_title(title,fontsize=12,pad=12)
    ax.set_xlabel('On minus off CPU seconds  (negative = on used less CPU)',fontsize=10)
    ax.grid(axis='x',alpha=.18)
axes[0].set_yticks(range(len(cases)),[c['case_id'].replace('__same_zone32plus32','').replace('__',' / ')for c in cases],fontsize=9)
axes[0].invert_yaxis()
fig.suptitle('Terminal-capacity screen: every fixed business case, both timing blocks',fontsize=15,y=.98)
fig.text(.5,.018,'Dots: two reversed-order fresh-process pairs. Diamond: their mean. Segments show the two observations, not confidence intervals.\nSame Snapshot/cache hashing and detached tick observer in both arms; at most three performance children with concurrent main-line work.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.065,1,.96))
fig.savefig(out/'all27_paired_cpu.png',dpi=160)
fig.savefig(out/'all27_paired_cpu.svg')
plt.close(fig)
meta={'input':str(source.resolve()),'input_sha256':sha256(source.read_bytes()).hexdigest(),
      'files':{p.name:sha256(p.read_bytes()).hexdigest()for p in out.iterdir()if p.is_file()},
      'cpu_seconds_after_imports':process_time()-cpu,'wall_seconds_after_imports':perf_counter()-wall,
      'scope':'Input read, all-case figure construction, PNG/SVG rendering and hashing; imports and final metadata output excluded. No new physics or routing.',
      'business_cases':len(cases),'paired_timing_repetitions':d['paired_repetitions']}
(out/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
(out/'plot.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(meta))
