"""Scientific figure from immutable recorded intervals; no new performance run."""
from pathlib import Path
import hashlib,json,time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
HERE=Path(__file__).resolve().parent; OUT=HERE.parent
source=OUT/'initial_owner_route_v3_independent_actual_review_001/report.json'
expected='6619c11ca5aca23cb7bb083a7198d5fd6b56e9b7697a5c700b12a93628e641a5'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(source)==expected
data=json.loads(source.read_bytes()); target=OUT/'initial_owner_v3_cost_figure_001'
assert not target.exists(); target.mkdir(); started=time.perf_counter()
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,
                     'axes.spines.left':False,'font.size':10,'svg.fonttype':'path'})
fields=[('admission_through_A_collection','接入至采集完成','#93c5fd'),
        ('collection_through_final_local_check','采集后至最终复核','#2563eb'),
        ('postcheck_through_last_observation','后续推进和观察','#a78bfa'),
        ('last_observation_to_finalization','观察至证据构造','#c4b5fd'),
        ('evidence_body_construction_normalization_encoding','证据构造、规范化、编码','#f59e0b'),
        ('outside_return_ledger_codec_tail','返回前账本、复制、编解码','#b45309')]
labels=[]; rows=list(data['rows'].items())
for key,row in rows:
    arm='默认' if key.endswith('/fixed_default') else '两候选'
    case=row['specification']['case']['case_id'].replace('block','B').replace('_load',' / L')
    fault=row['specification']['fault']
    prefix=case if fault=='normal' else {'initial_ack_drop3':'初始回执丢失',
        'postsubmit_source_outage':'A 执行中断','postsubmit_B_execution_outage':'B 执行中断'}[fault]
    labels.append(prefix+' · '+arm+(' 〔未闭合〕' if not row['root']['closed'] else ''))
fig,ax=plt.subplots(figsize=(13.4,9.4),layout=None)
y=list(range(len(rows))); left=[0.]*len(rows)
for field,title,color in fields:
    values=[r['warm_boundary_partition_ms'][field] for _,r in rows]
    ax.barh(y,values,left=left,height=.67,label=title,color=color,edgecolor='white',linewidth=.3)
    left=[a+b for a,b in zip(left,values)]
for i,((key,row),total) in enumerate(zip(rows,left)):
    assert abs(total-row['root']['warm_ms'])<1e-8
    ax.text(total+20,i,f'{total:,.1f}',va='center',fontsize=8.8,color='#334155')
ax.axvline(100,color='#dc2626',linestyle='--',linewidth=1.5,label='100ms 目标')
ax.set_yticks(y,labels,fontproperties=font,fontsize=10)
ax.invert_yaxis(); ax.set_xlim(0,4100);ax.set_xlabel('完整请求墙钟时间（ms）',fontproperties=font,labelpad=10)
ax.xaxis.grid(True,color='#e2e8f0',linewidth=.7);ax.set_axisbelow(True)
ax.tick_params(axis='y',length=0,pad=9)
for boundary in (3.5,7.5,11.5,13.5,15.5): ax.axhline(boundary,color='#e2e8f0',linewidth=.6)
fig.text(.04,.965,'完整请求成本：证据处理占据主要时间',fontproperties=font,fontsize=19,weight='bold',color='#0f172a')
fig.text(.04,.927,'实际 18 分支：16 个闭合、2 个未闭合；0 / 18 达到 100ms。全部时间保留，不扣除共享工作。',fontproperties=font,fontsize=11,color='#475569')
handles,legend_labels=ax.get_legend_handles_labels()
fig.legend(handles,legend_labels,loc='lower left',bbox_to_anchor=(.035,.078),ncol=3,
           prop=font,frameon=False,columnspacing=1.8,handlelength=2)
fig.text(.04,.053,'区间来自互不重叠的已记录边界，逐项精确加回请求总时间；并非单个函数的独占计时。',fontproperties=font,fontsize=9,color='#475569')
fig.text(.04,.032,'冷启动 744.466ms、关闭及清理 205.942ms；整轮 92.9546363s 单独保留，不摊薄。有限两候选不代表完整 32 候选达标。',fontproperties=font,fontsize=9,color='#475569')
fig.text(.04,.012,'来源：initial_owner_route_v3_independent_actual_review_001 / SHA256 '+expected[:16]+'…',fontsize=8,color='#64748b')
fig.subplots_adjust(left=.245,right=.96,top=.89,bottom=.205)
for ext in ('png','svg'): fig.savefig(target/('request_costs.'+ext),dpi=180,facecolor='white')
plt.close(fig)
receipt={'status':'saved_figure_from_immutable_recorded_intervals','source_sha256':expected,
    'producer_sha256':sha(__file__),'matplotlib':matplotlib.__version__,
    'artifacts':{n:sha(target/n) for n in ('request_costs.png','request_costs.svg')},
    'new_native_calls':0,'new_predictor_calls':0,'creation_seconds':time.perf_counter()-started,
    'scope':'No remeasurement or excluded cost; six recorded disjoint intervals for all18 rows.'}
(target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
print(json.dumps({'path':str(target/'request_costs.png'),'receipt_sha256':sha(target/'receipt.json')}))
