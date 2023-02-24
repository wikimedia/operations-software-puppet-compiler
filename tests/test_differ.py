import unittest
from copy import deepcopy
from pathlib import Path

import mock

from puppet_compiler.differ import PuppetCatalog, PuppetResource


class TestPuppetResource(unittest.TestCase):
    def setUp(self):
        self.raw_resource = {
            "type": "Class",
            "title": "hhvm",
            "exported": False,
            "parameters": {
                "ensure": "present",
                "type": "fcgi",
                "settings": {"foo": 1, "bar": [2, 3]},
                "before": ["Class[apache2]"],
                "nope": None,
            },
        }

        self.r = PuppetResource(
            self.raw_resource,
        )

    def test_str(self):
        """Test stringification"""
        self.assertEqual(str(self.r), "Class[hhvm]")

    def test_is_same(self):
        """Test function `PuppetResource.is_same_of`"""
        other = mock.MagicMock()
        other.__str__.return_value = "Class[hhvm]"
        self.assertTrue(self.r.is_same_of(other))
        other.__str__.return_value = "Hhvm::monitoring[test]"
        self.assertFalse(self.r.is_same_of(other))

    def test_equality(self):
        other = PuppetResource(self.raw_resource)
        self.assertEqual(self.r, other)
        other.content = "lala"
        self.assertNotEqual(self.r, other)

    @mock.patch("difflib.unified_diff")
    @mock.patch("puppet_compiler.differ.parameters_diff")
    def test_diff_if_present(self, datadiff_mock, difflib_mock):
        other = PuppetResource(self.raw_resource)
        self.assertIsNone(self.r.diff_if_present(other))
        # Now let's add some content
        self.r.resource_type = "File"
        other.resource_type = "File"
        other.content = "lala\nalal"
        diff = self.r.diff_if_present(other)
        datadiff_mock.assert_not_called()
        difflib_mock.assert_called_with([], ["lala", "alal"], lineterm="", fromfile="hhvm.orig", tofile="hhvm")
        self.r.resource_type = "Class"
        datadiff_mock.reset_mock()
        difflib_mock.reset_mock()
        # Resource with different params, it should be different
        different_params_raw_resource = deepcopy(self.raw_resource)
        different_params_raw_resource["parameters"]["ensure"] = "absent"
        other = PuppetResource(different_params_raw_resource)
        diff = self.r.diff_if_present(other)
        difflib_mock.assert_not_called()
        datadiff_mock.assert_called_with(
            self.r.parameters, other.parameters, fromfile="Class[hhvm].orig", tofile="Class[hhvm]"
        )
        self.assertNotIn("content", diff)
        self.assertIn("parameters", diff)


class TestPuppetCatalog(unittest.TestCase):
    def setUp(self):
        fixtures = Path(__file__).parent.resolve() / "fixtures"
        self.orig = PuppetCatalog(fixtures / "catalog.pson")
        self.change = PuppetCatalog(fixtures / "catalog-change.pson")

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.orig.name, "test123.test")
        self.assertIsInstance(self.orig.resources, dict)

    def test_core_resources(self):
        """Test core resources."""
        # The lists below are not exhaustive and only contain resources in the test catalogue
        invalid_core_resources = ("Class", "Notify", "Systemd::Unit", "Stage")
        valid_core_resources = ("File", "Package", "Exec")
        for resource in self.orig.core_resources:
            assert not resource.startswith(invalid_core_resources)
            assert resource.startswith(valid_core_resources)

    def test_diff_is_present(self):
        self.assertIsNone(self.orig.diff_if_present(self.orig))
        diffs = self.orig.diff_if_present(self.change)
        self.assertEqual(diffs["total"], 24)
        self.assertEqual(diffs["only_in_self"], set(["Class[Sslcert]", "Package[orig_catalog]"]))
        self.assertEqual(diffs["only_in_other"], set(["Class[Sslcert3]", "Package[other_catalog]"]))
        self.assertEqual(len(diffs["resource_diffs"]), 3)
        self.assertEqual(diffs["perc_changed"], "29.17%")

    def test_diff_is_present_core(self):
        self.assertIsNone(self.orig.diff_if_present(self.orig, True))
        diffs = self.orig.diff_if_present(self.change, True)
        self.assertEqual(diffs["total"], 24)
        self.assertEqual(diffs["only_in_self"], set(["Package[orig_catalog]"]))
        self.assertEqual(diffs["only_in_other"], set(["Package[other_catalog]"]))
        self.assertEqual(len(diffs["resource_diffs"]), 1)
        self.assertEqual(diffs["perc_changed"], "12.50%")
