"""Independent saved004 readback; no new native session or projection."""
from pathlib import Path
import json
from . import audit_live_obligation_native_saved as prior

if __name__=='__main__':
    folder=prior.OUT/'live_obligation_native_probe_prepare_004'
    target=prior.OUT/'live_obligation_native_saved_review_004.json'
    prior.require(not target.exists(),'immutable_review')
    report=prior.audit(folder)
    receipt=prior.read(folder/'receipt.json')
    prior.require(receipt['status']=='complete3_assessed','producer_status')
    for row in report['rows'].values():
        prior.require(row['producer_status']==row['assessment_preserved']=='assessed','branch_assessed')
        prior.require(all(s['verified'] is True and s['fallback_used'] is False and s['selected_action_admitted'] is True
                          for s in row['stages']),'both_information_stages_and_actions')
        row['reported_strict_protection']=receipt['comparisons'][next(k for k,v in report['rows'].items() if v is row)]['strict_protected']
    prior.require(receipt['comparisons']['mechanism/vector_25']['strict_protected'] is True,'selected_protection')
    prior.require(receipt['comparisons']['mechanism/vector_24']['strict_protected'] is False,'negative_control')
    report.update(status='verified_three_assessed_fixed_native_branches',assessed=3,unknown=0,
        diagnosis='Typed stationary E-loading availability now matches accepted native capture. All six initial owner inputs and all six later collections pass saved endpoint replay; no first-return fallback. Fifteen per-job completion times exactly match the prior saved pure003 actions.',
        next_causal_question='Close the unchanged three-case32-action domain and both16-member references; current3 cannot establish a full native optimum or online search advantage.',
        limits=['Only three fixed vectors in mechanism; no complete16/32/96 native reference families',
                'All three native fixed actions admitted under actual owned views and delivered captures, but source-state stability remains conditional, not a global synchronization proof',
                'Five-job strict protection is established only for these actual completed trajectories against executed vector12',
                'No native or predictor execution in this audit; saved endpoint/physical replay only',
                'No novelty, online optimization, original-map applicability, or100ms claim'],
        audit_source=prior.ref(__file__),reused_saved_audit_source=prior.ref(prior.__file__))
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'report':prior.ref(target),'elapsed':report['elapsed_wall_seconds']}))
