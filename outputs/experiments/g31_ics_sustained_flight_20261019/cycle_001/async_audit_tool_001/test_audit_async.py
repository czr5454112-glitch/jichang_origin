"""Independent auditor checks using an already closed native run; starts no native process."""
import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('independent_async_audit', HERE/'audit_async.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = HERE.parent/'A2_train_prefer8_001'
        cls.raw, _, _ = audit.load_closed(cls.folder)
        cls.decision = next(row for row in cls.raw['repeated_decisions']
            if row['current_admission']['execution_mode'] == 'protected_current')

    def test_actual_complete_current_guard_submit_ack_edge(self):
        current = audit.current_chain(self.raw, self.decision)
        self.assertEqual(current['status'], 'passed')
        self.assertEqual(current['edge']['to'], 8)
        self.assertTrue(all(value <= .05 for value in current['source_ages_sim_s'].values()))

    def test_sync_does_not_become_async_positive(self):
        result = audit.audit(self.folder)
        self.assertEqual(result['closed_current_chains'], 2)
        self.assertEqual(result['consumed_ranked_bodies'], 0)
        self.assertEqual(result['status'], 'not_yet_positive_async_witness')
        self.assertFalse(result['full_request_100ms_certified'])

    def test_wrong_native_leg_rejected(self):
        raw = copy.deepcopy(self.raw)
        next(row for row in raw['result']['receipts'] if row['event'] == 'LEG_START'
            and row['business_bag_id'] == 'reuse2')['transport_leg_id'] = 'wrong-leg'
        with self.assertRaisesRegex(ValueError, 'native_loaded_leg_edge_identity'):
            audit.current_chain(raw, self.decision)

    def test_point05_expiry_rejected(self):
        raw = copy.deepcopy(self.raw)
        source = raw['repeated_attempts']['B'][0]['model_report']['seed']['bundle']['source_records'][0]
        source['captured_at'] = self.decision['selected_at'] - .0500001
        with self.assertRaisesRegex(ValueError, 'actual_current_point05_source_age'):
            audit.current_chain(raw, self.decision)

    def test_missing_business_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw['repeated_attempts']['B'][0]['model_report']['candidate_results']['prefer_8']['completion'].pop('blocker')
        with self.assertRaisesRegex(ValueError, 'complete_candidate_prediction'):
            audit.current_chain(raw, self.decision)

    def test_generation_mismatch_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw['outbox'][self.decision['command_id']]['request']['expected_generation'] += 1
        with self.assertRaisesRegex(ValueError, 'actual_chosen_submit_identity'):
            audit.current_chain(raw, self.decision)

    def test_available_body_without_selected_consumption_rejected(self):
        current = audit.current_chain(self.raw, self.decision)
        with self.assertRaisesRegex(ValueError, 'selected_decision_must_identify_worker_body'):
            audit.async_chain(self.folder, self.raw, {}, self.decision, current, {'records': []})

    def test_real_body_with_refused_current_guard_never_becomes_execution_success(self):
        folder = HERE.parent/'A4_train_async_001'
        if not folder.exists():
            self.skipTest('separately registered A4 run unavailable')
        result = audit.audit(folder)
        self.assertEqual(len(result['delivered_bodies']), 1)
        self.assertEqual(result['delivered_bodies'][0]['status'], 'bound_actual_complete_body_only_not_execution')
        self.assertTrue(result['delivered_bodies'][0]['native_progress_observed'])
        self.assertEqual(result['delivered_bodies'][0]['downstream'][0]['enabled_candidate_count'], 0)
        self.assertEqual(result['consumed_submitted_ack_edge_chains'], 0)
        self.assertFalse(result['complete_successful_run'])
        self.assertEqual(result['status'], 'not_yet_positive_async_witness')

    def test_worker_order_requires_all_original_jobs_in_each_candidate(self):
        body = audit.read(HERE.parent/'A4_train_async_001/resident_B/B-00001.json')
        jobs = {row['business_bag_id'] for row in self.raw['input']['jobs']}
        self.assertEqual(audit.complete_worker_order(body, jobs)[0], 'prefer_8')
        for failure in ('empty', 'missing', 'negative', 'nan', 'bool', 'status'):
            with self.subTest(failure=failure):
                corrupt = copy.deepcopy(body)
                prediction = corrupt['model_report']['candidate_results']['prefer_8']
                if failure == 'empty':
                    prediction['completion'] = {}
                elif failure == 'missing':
                    prediction['completion'].pop('blocker')
                elif failure == 'status':
                    prediction['status'] = 'unknown'
                else:
                    prediction['completion']['blocker'] = {'negative': -1., 'nan': float('nan'), 'bool': False}[failure]
                with self.assertRaisesRegex(ValueError, 'complete_worker_candidate_prediction'):
                    audit.complete_worker_order(corrupt, jobs)

    def test_worker_order_refuses_missing_action_or_unknown_model(self):
        body = audit.read(HERE.parent/'A4_train_async_001/resident_B/B-00001.json')
        jobs = {row['business_bag_id'] for row in self.raw['input']['jobs']}
        for field in ('candidate_results', 'status'):
            corrupt = copy.deepcopy(body)
            if field == 'status':
                corrupt['model_report']['status'] = 'unknown'
            else:
                corrupt['model_report']['candidate_results'].pop('native_default')
            with self.assertRaisesRegex(ValueError, 'supported_complete_worker_candidate_set'):
                audit.complete_worker_order(corrupt, jobs)

    def test_same_sim_time_activation_does_not_establish_worker_interval_progress(self):
        body = {'worker_started_ns': 100, 'worker_completed_ns': 200}
        raw = {'owner_activation_admissions': [
            {'accepted_wall_ns': 99, 'accepted_at': 1.},
            {'accepted_wall_ns': 110, 'accepted_at': 2.},
            {'accepted_wall_ns': 190, 'accepted_at': 2.},
            {'accepted_wall_ns': 201, 'accepted_at': 3.}]}
        result = audit.activation_progress(raw, body)
        self.assertFalse(result['observed'])
        self.assertEqual(result['native_activations'], 2)
        raw['owner_activation_admissions'][2]['accepted_at'] = 2.01
        result = audit.activation_progress(raw, body)
        self.assertTrue(result['observed'])
        self.assertEqual(result['distinct_sim_times'], [2., 2.01])
        self.assertFalse(result['physical_events_bound_to_worker_wall_interval'])


if __name__ == '__main__':
    unittest.main()
