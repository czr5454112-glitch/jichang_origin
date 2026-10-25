import unittest
import compare_actual as c


def controls():
    ref = {c.parent.FLAG: True, 'end_time': 98259, 'source_fifo_order': 'canonical',
           'source_fifo': True, 'enable_ebs_predecessor_gate': True}
    return dict(ref, **{c.FLAG: True}), ref


class Tests(unittest.TestCase):
    def test_parent_missing_flag_means_registered_false_only(self):
        value = c.check_controls(*controls())
        self.assertFalse(value['same_binary'])
        self.assertIn('not full-population', value['boundary'])

    def test_samebinary_requires_explicit_false(self):
        a, b = controls()
        with self.assertRaises(ValueError): c.check_controls(a, b, same_binary=True)
        b[c.FLAG] = False
        self.assertTrue(c.check_controls(a, b, same_binary=True)['same_binary'])

    def test_edf_dependency_and_bool_types(self):
        for key, value in [(c.FLAG, 1), (c.parent.FLAG, False), (c.parent.FLAG, 1)]:
            a, b = controls(); a[key] = value
            with self.assertRaises(ValueError): c.check_controls(a, b)

    def test_reference_edf_off_is_not_sole_class_contrast(self):
        a, b = controls(); b[c.parent.FLAG] = False
        with self.assertRaises(ValueError): c.check_controls(a, b)

    def test_other_control_change_either_direction(self):
        for which in (0, 1):
            pair = list(controls()); pair[which]['new_parameter'] = 1
            with self.assertRaises(ValueError): c.check_controls(*pair)

    def test_ebs_model_cannot_change(self):
        a, b = controls(); a['source_fifo_order'] = b['source_fifo_order'] = 'ready_first'
        with self.assertRaises(ValueError): c.check_controls(a, b)

    def test_freeze_requires_defaultfalse_parity(self):
        v = {'schema': 'g31.candidate024.comparison_binding.v1', 'passed': True,
             'default_false_parity_passed': True, 'build_micro_five_gates_passed': True,
             'source_sha256': c.SOURCE, 'binary_sha256': 'a'*64}
        c.verify_binding(v)
        v['default_false_parity_passed'] = False
        with self.assertRaises(ValueError): c.verify_binding(v)

    def test_inherits_edf_repeat_counter_checks(self):
        native = {'planning_attempts': 100000, 'source_attempt_edf': {'valid_source_attempts': 100000,
                  'already_overdue_valid_attempts': 40000, 'count_scope': 'valid repeated attempts'}}
        self.assertTrue(c.parent.check_counters(native, True)['passed'])
        native['source_attempt_edf']['valid_source_attempts'] -= 1
        with self.assertRaises(ValueError): c.parent.check_counters(native, True)


if __name__ == '__main__':
    unittest.main()
