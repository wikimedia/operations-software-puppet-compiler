import unittest
from puppet_compiler import state


class TestChangeState(unittest.TestCase):
    def test_init(self):
        test = state.ChangeState('change', 'test.example.com', False, True, None)
        self.assertEqual(test.mode, 'change')
        self.assertEqual(test.host, 'test.example.com')
        self.assertFalse(test.prod_error)
        self.assertTrue(test.change_error)
        self.assertIsNone(test.diff)

    def test_name(self):
        test = state.ChangeState('change', 'test.example.com', False, True, None)
        # Prod compiled, change failed
        self.assertEqual(test.name, 'error')
        # Prod compiled, change too, no diffs
        test.change_error = False
        self.assertEqual(test.name, 'noop')
        # Diff failed to be created
        test.diff = False
        self.assertEqual(test.name, 'fail')
        # There are diffs
        test.diff = True
        self.assertEqual(test.name, 'diff')
        # Both prod and change failed
        test = state.ChangeState('change', 'test.example.com', True, True, None)
        self.assertEqual(test.name, 'fail')
        # Prod failed, change didn't
        test = state.ChangeState('change', 'test.example.com', True, False, None)
        self.assertEqual(test.name, 'noop')


class TestStatesCollection(unittest.TestCase):

    def test_add(self):
        collection = state.StatesCollection()
        test = state.ChangeState('test', 'test.example.com', True, False, None)  # noop
        collection.add(test)
        self.assertEqual(collection.modes['test']['noop'], set(['test.example.com']))

    def test_mode_to_str(self):
        collection = state.StatesCollection()
        test = state.ChangeState('test', 'test.example.com', True, False, None)  # noop
        collection.add(test)
        test2 = state.ChangeState('test', 'test.example.com', False, False, True)  # diff
        collection.add(test2)
        self.assertEqual(collection.mode_to_str('nonexistent'), '[nonexistent] Nodes: ')
        self.assertRegexpMatches(collection.mode_to_str('test'), ' 1 DIFF ')


class TestFutureState(TestChangeState):

    def test_name(self):
        # Production works, future does not
        test = state.FutureState('change', 'test.example.com', False, True, None)
        self.assertEqual('error', test.name)
        # Prod compiled, future too, no diffs
        test.change_error = False
        self.assertEqual(test.name, 'ok')
        # Diff failed to be created
        test.diff = False
        self.assertEqual(test.name, 'error')
        # There are diffs
        test.diff = True
        self.assertEqual(test.name, 'diff')
        # Both prod and future failed
        test = state.FutureState('change', 'test.example.com', True, True, None)
        self.assertEqual(test.name, 'break')
        # Prod failed, change didn't
        test = state.FutureState('change', 'test.example.com', True, False, None)
        self.assertEqual(test.name, 'break')
