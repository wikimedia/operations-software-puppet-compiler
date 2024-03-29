import unittest

from puppet_compiler import state


class TestChangeState(unittest.TestCase):
    def test_init(self):
        test = state.ChangeState("test.example.com", False, True, None, None)
        self.assertEqual(test.host, "test.example.com")
        self.assertFalse(test.base_error)
        self.assertTrue(test.change_error)
        self.assertIsNone(test.has_diff)
        self.assertIsNone(test.has_core_diff)

    def test_name(self):
        test = state.ChangeState(
            host="test.example.com",
            base_error=False,
            change_error=True,
            has_diff=None,
            has_core_diff=None,
        )
        # Prod compiled, change failed
        self.assertEqual(test.name, "error")

        # Prod compiled, change too, no diffs
        test.change_error = False
        self.assertEqual(test.name, "noop")

        # Diff failed to be created
        test.has_diff = False
        self.assertEqual(test.name, "fail")

        # There are diffs
        test.has_diff = True
        self.assertEqual(test.name, "diff")

        # There are diffs
        test.has_core_diff = True
        self.assertEqual(test.name, "core_diff")

        # Both prod and change failed
        test = state.ChangeState("test.example.com", True, True, None, None)
        self.assertEqual(test.name, "fail")

        # Prod failed, change didn't
        test = state.ChangeState("test.example.com", True, False, None, None)
        self.assertEqual(test.name, "noop")


class TestStatesCollection(unittest.TestCase):
    def test_add(self):
        collection = state.StatesCollection()
        test = state.ChangeState("test.example.com", True, False, None, None)  # noop
        collection.add(test)
        self.assertEqual(collection.states["noop"], set(["test.example.com"]))

    def test_summary(self):
        collection = state.StatesCollection()
        test = state.ChangeState("test.example.com", True, False, None, None)  # noop
        collection.add(test)
        test2 = state.ChangeState("test.example.com", False, False, True, False)  # diff
        collection.add(test2)
        test2 = state.ChangeState("test.example.com", False, False, True, True)  # core_diff
        collection.add(test2)
        self.assertRegexpMatches(collection.summary(), " 1 DIFF ")
        self.assertRegexpMatches(collection.summary(), " 1 CORE_DIFF ")
