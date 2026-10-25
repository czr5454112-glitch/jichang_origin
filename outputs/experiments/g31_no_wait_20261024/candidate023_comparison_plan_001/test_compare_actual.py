import copy
import unittest
import compare_actual as c


def controls():
    off = {c.FLAG: False, 'end_time': 98259, 'source_fifo_order': 'canonical', 'source_fifo': True,
           'enable_ebs_predecessor_gate': True, 'max_depth': 1}
    return off, dict(off, **{c.FLAG: True})


def native():
    return {'planning_attempts': 100, 'source_attempt_edf': {'valid_source_attempts': 100,
        'already_overdue_valid_attempts': 75, 'count_scope': 'Actual source attempts after guards'}}


def full_row():
    stats = {'count': 28506, 'mean': 100., 'p95': 200., 'p99': 300., 'max': 400.}
    return {'status': 'complete', 'usable_reported_result': True, 'all_five_passed': True,
        'metrics': {'business_denominator': 28506, 'completed_businesses': 28506,
            'segment_denominator': 43603, 'completed_segments': 43603, 'full_population_available': True,
            **{k: dict(stats) for k in ('user_tht', 'network_elapsed', 'planning_retry_wait', 'preplanning', 'canonical_elapsed')},
            **{k: {'status': 'available', 'denominator': 28506, 'count': 10} for k in ('STD', 'STD_minus_2700')}}}


def tht():
    return {'passed': True, 'business_denominator': 28506, 'completed_businesses': 28506,
        'user_tht_full_population_available': True,
        'user_tht': {'full_population': {'count': 28506, 'sum': 28506*100., 'mean': 100.}},
        'secondary': {'business_sum_activation_to_first_planning': {'full_population': {'count': 28506, 'sum': 28506*200., 'mean': 200.}}}}


class Tests(unittest.TestCase):
    def test_sole_flag_and_raw_physics_comes_from_contract(self):
        self.assertTrue(c.check_controls(*controls())['passed'])
        self.assertTrue(c.check_controls({c.FLAG: False, 'end_time': 98259}, {c.FLAG: True, 'end_time': 98259}, effective=False)['passed'])

    def test_key_union_rejects_extra_in_either_arm(self):
        for side in (0, 1):
            pair = list(controls()); pair[side]['hidden_parameter'] = 1
            with self.assertRaises(ValueError): c.check_controls(*pair)

    def test_bool_impostor_and_source_policy_change(self):
        for value in (0, None, 'false'):
            off, on = controls(); off[c.FLAG] = value
            with self.assertRaises(ValueError): c.check_controls(off, on)
        off, on = controls(); off['source_fifo_order'] = on['source_fifo_order'] = 'ready_first'
        with self.assertRaises(ValueError): c.check_controls(off, on)

    def test_fullrow_and_each_failed_gate(self):
        c.require_full_row(full_row())
        for key in ('usable_reported_result', 'all_five_passed'):
            row = full_row(); row[key] = False
            with self.assertRaises(ValueError): c.require_full_row(row)

    def test_censoring_never_uses_completed_subset(self):
        for key, value in [('completed_businesses', 28505), ('completed_segments', 43602), ('full_population_available', False)]:
            row = full_row(); row['metrics'][key] = value
            with self.assertRaises(ValueError): c.require_full_row(row)

    def test_deadline_denominators_and_finite_tail(self):
        row = full_row(); row['metrics']['STD_minus_2700']['denominator'] = 28505
        with self.assertRaises(ValueError): c.require_full_row(row)
        row = full_row(); row['metrics']['user_tht']['p99'] = float('nan')
        with self.assertRaises(ValueError): c.require_full_row(row)

    def test_counters_are_repeated_attempts_not_distinct_population(self):
        value = native(); value['planning_attempts'] = 300000
        value['source_attempt_edf'].update(valid_source_attempts=300000, already_overdue_valid_attempts=200000)
        self.assertTrue(c.check_counters(value, True)['passed'])

    def test_counter_corruption_and_types(self):
        for field, value in [('valid_source_attempts', 99), ('valid_source_attempts', True), ('already_overdue_valid_attempts', 101), ('already_overdue_valid_attempts', -1)]:
            data = native(); data['source_attempt_edf'][field] = value
            with self.assertRaises(ValueError): c.check_counters(data, True)

    def test_off_requires_absent_on_requires_present(self):
        self.assertTrue(c.check_counters({'planning_attempts': 100}, False)['passed'])
        with self.assertRaises(ValueError): c.check_counters(native(), False)
        with self.assertRaises(ValueError): c.check_counters({'planning_attempts': 100}, True)

    def test_ready_mean_is_sum_identity_only(self):
        value = c.derived_ready(tht(), True)
        self.assertEqual(value['mean'], 300.)
        self.assertIsNone(value['p95']); self.assertIsNone(value['max'])

    def test_ready_missing_bad_count_and_censor_null(self):
        for key, value in [('passed', False), ('completed_businesses', 28505), ('user_tht_full_population_available', False)]:
            t = tht(); t[key] = value
            self.assertIsNone(c.derived_ready(t, True)['mean'])
        t = tht(); t['secondary'] = {}
        self.assertIsNone(c.derived_ready(t, True)['mean'])
        t = tht(); t['secondary']['business_sum_activation_to_first_planning']['full_population']['count'] -= 1
        self.assertIsNone(c.derived_ready(t, True)['mean'])

    def test_unbound_binary_and_wrong_source_rejected(self):
        binding = {'schema': 'g31.candidate023.comparison_binding.v1', 'passed': True, 'build_and_micro_passed': True,
                   'source_sha256': c.SOURCE, 'binary_sha256': 'a'*64, 'parent_comparison_plan_sha256': c.PLAN_SHA}
        c.verify_binding(binding)
        for key, value in [('binary_sha256', None), ('source_sha256', 'foreign'), ('build_and_micro_passed', False)]:
            b = copy.deepcopy(binding); b[key] = value
            with self.assertRaises(ValueError): c.verify_binding(b)


if __name__ == '__main__':
    unittest.main()
