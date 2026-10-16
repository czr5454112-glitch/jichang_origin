"""Register read-only paper review without importing any project modules."""
import hashlib
import json
from pathlib import Path

ROOT = Path(r'C:/PROGRAMING/czr005/.g31_ics_circulation_worktree')
HERE = Path(__file__).resolve().parent
DOWNLOADS = Path(r'C:/Users/38908/Downloads')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


rows = [
    ('Synthesis_of_Distributed_and_Decentralized_Supervisory_Control_via_Contract_Negotiation.pdf',
     'fb9929b5ea1b61bf5f03afe415e539b818d944033c0d37a92d9764d1aad439d3',
     'distributed_contract_negotiation_pdf_review_001.json',
     '0211a792b8932c8c80a4f6e5c864c3dff4e32e46169da374150bbb395c54adc2'),
    ('1-s2.0-S1751570X26001093-main.pdf',
     'a60996dc6fc4d5628a6cd4b471ef8dcc3c7651c5a49f6b8385be9c75a2ce9f5e',
     'contract_uncertainty_paper_review_20261016_001.json', None),
    ('Learning_Optimal_Baggage_Routing_from_Expert_Demonstrations.pdf',
     'cfdaebaa4ddf8cdfbb9412ffab3dd3b6516bff08afff9a365baad71a8cf7b818',
     'learning_baggage_expert_paper_review_001.json',
     '8e8527031dc18bd8aa193f8c1f2e6d0642e61d6b13f5359de3d171c54a57ffb1'),
    ('T2BR_A_Hierarchical_Repositioning_Approach_for_Autonomous_Mobility_on_Demand_Systems.pdf',
     'a14ceced02a4b10a5a53387852a5f531dc28ca738b1e20ed2693c457d53e73e1',
     'T2BR_readonly_research_001.json',
     '465735e922440c7a650c3708f00b5b9c79581326d308f2810957a737494a59de'),
]
records = []
for pdf_name, pdf_expected, note_name, note_expected in rows:
    pdf, note = DOWNLOADS / pdf_name, HERE / note_name
    pdf_actual, note_actual = digest(pdf), digest(note)
    if pdf_actual != pdf_expected:
        raise ValueError('PDF changed: ' + pdf_name)
    if note_expected is not None and note_actual != note_expected:
        raise ValueError('Review changed: ' + note_name)
    content = json.loads(note.read_text(encoding='utf-8'))
    if not isinstance(content, dict) or not content.get('schema'):
        raise ValueError('Review schema missing: ' + note_name)
    records.append({'pdf': str(pdf), 'pdf_sha256': pdf_actual,
                    'note': str(note), 'note_sha256': note_actual,
                    'note_schema': content['schema']})

doc = ROOT / 'docs/g31_ics_circulation/LT2_METHOD_COMPARISON_20261014.md'
backup = HERE / 'four_papers_method_comparison_before001.snapshot'
if digest(backup) != 'e61505b0bdc605a76ed082ef9edd7b05ecd2192942620dc0bb44f2aaba763609':
    raise ValueError('Prior method comparison backup changed')
if not doc.read_text(encoding='utf-8').startswith(backup.read_text(encoding='utf-8').rstrip()):
    raise ValueError('Prior method comparison was not preserved')

result = {
    'schema': 'g31.four_supplied_papers.review_manifest.v1',
    'status': 'literature_review_registered_not_method_validation',
    'date_local': '2026-10-16',
    'papers': records,
    'method_comparison': {'path': str(doc), 'sha256': digest(doc)},
    'method_comparison_before': {'path': str(backup), 'sha256': digest(backup)},
    'root_independent_readback': [
        'All four structured notes parsed and read; all original PDF hashes checked.',
        'Contract DES: independently read PDF pages1,11,12,13 text, confirming instantaneous signaling, unresolved general termination and two-subsystem boundary.',
        'Contract stochastic games: root read main text pages1-21 and visually inspected complete pages5,20; appendix proofs were not independently verified.',
        'Baggage learning: root visually inspected complete PDF pages5,6 including experimental setup, TableI, Fig5 and nonuniform performance claims.',
        'T2BR: root visually inspected complete PDF page9 including TableIV and fleet-batch timing definition; no100ms extrapolation.'
    ],
    'prior_history_used': [
        'docs/g31_ics_circulation/NOVELTY_LEDGER.md',
        'docs/g31_ics_circulation/NEXT_ACTION.md',
        'outputs/experiments/g31_ics_lt2_sustained_20261014/user_resume_20261015_001/decentralized_empty_prediction_literature_20261016_001.json'
    ],
    'recommended_order': [
        'Complete prospective same-information online comparison and saved physical checks.',
        'Test event-triggered conditional suffix updates and lower-feasibility/value feedback under existing owner and message rights.',
        'Study small shared-interface behavioral contract compatibility/nonblocking, without importing synchronous communication or full-state observation assumptions.',
        'Only then test a small lawful-observation demonstration ranker on grouped held-out inputs; retain full32 references and separate any later budgeted-provider revision.'
    ],
    'research_claims': {
        'new_theorem': False, 'paper_replication': False,
        'new_method_validated': False, 'whole_day_goal_met': False,
        'complete_request_100ms_met': False, 'joint_advantage_established': False
    },
    'paper_review_scope': {
        'source_pdfs_modified': False, 'engineering_sources_modified': False,
        'native_runs': 0, 'model_runs': 0, 'training_runs': 0,
        'external_messages_sent': 0, 'checkpoint_milestone_advanced': False
    },
    'registrar': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__))}
}
target = HERE / 'four_papers_review_manifest_20261016_001.json'
with target.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
saved = json.loads(target.read_text(encoding='utf-8'))
if saved != result:
    raise ValueError('Manifest readback differs')
print(json.dumps({'status': result['status'], 'papers': len(records),
                  'manifest': str(target), 'sha256': digest(target),
                  'method_comparison_sha256': digest(doc)}, ensure_ascii=False))
