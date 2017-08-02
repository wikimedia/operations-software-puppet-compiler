import mock
import os
import unittest

from puppet_compiler.differ import PuppetResource, PuppetCatalog
from puppet_compiler.worker import future_filter


class TestPuppetResource(unittest.TestCase):

    def setUp(self):
        self.raw_resource = {
            'type': 'Class',
            'title': 'hhvm',
            'exported': False,
            'parameters': {
                'ensure': 'present',
                'type': 'fcgi',
                'settings': {'foo': 1, 'bar': [2, 3]},
                'before': ['Class[apache2]'],
                'nope': None,
            }
        }
        self.r = PuppetResource(
            self.raw_resource,
            future_filter,
        )

    def test_init(self):
        """Test initialization"""
        self.assertEqual(self.r.resource_type, 'Class')
        self.assertEqual(self.r.title, 'hhvm')
        self.assertEqual(self.r._filter, future_filter)
        self.assertEqual(self.r.content, '')
        self.assertEqual(self.r.parameters['before'], 'Class[apache2]')
        self.assertEqual(self.r.parameters['settings'], {'foo': '1', 'bar': ['2', '3']})
        self.assertNotIn('nope', self.r.parameters)

    def test_str(self):
        """Test stringification"""
        self.assertEqual(str(self.r), 'Class[hhvm]')

    def test_is_same(self):
        """Test function `PuppetResource.is_same_of`"""
        other = mock.MagicMock()
        other.__str__.return_value = 'Class[hhvm]'
        self.assertTrue(self.r.is_same_of(other))
        other.__str__.return_value = 'Hhvm::monitoring[test]'
        self.assertFalse(self.r.is_same_of(other))

    def test_equality(self):
        # Not filtered resource, it should be different
        other = PuppetResource(self.raw_resource)
        self.assertNotEqual(self.r, other)
        other = PuppetResource(self.raw_resource, future_filter)
        self.assertEqual(self.r, other)
        other.content = 'lala'
        self.assertNotEqual(self.r, other)

    @mock.patch('difflib.unified_diff')
    @mock.patch('puppet_compiler.differ.parameters_diff')
    def test_diff_if_present(self, datadiff_mock, difflib_mock):
        other = PuppetResource(self.raw_resource, future_filter)
        self.assertIsNone(self.r.diff_if_present(other))
        # Now let's add some content
        self.r.resource_type = 'File'
        other.resource_type = 'File'
        other.content = "lala\nalal"
        diff = self.r.diff_if_present(other)
        datadiff_mock.assert_not_called()
        difflib_mock.assert_called_with(
            [], ['lala', 'alal'],
            lineterm="",
            fromfile='hhvm.orig',
            tofile='hhvm'
        )
        self.r.resource_type = 'Class'
        datadiff_mock.reset_mock()
        difflib_mock.reset_mock()
        # Not filtered resource, it should be different
        other = PuppetResource(self.raw_resource)
        diff = self.r.diff_if_present(other)
        difflib_mock.assert_not_called()
        datadiff_mock.assert_called_with(
            self.r.parameters, other.parameters,
            fromfile='Class[hhvm].orig', tofile='Class[hhvm]'
        )
        self.assertNotIn('content', diff)
        self.assertIn('parameters', diff)


class TestPuppetCatalog(unittest.TestCase):

    def setUp(self):
        fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        self.orig = PuppetCatalog(os.path.join(fixtures, 'catalog.pson'))
        self.change = PuppetCatalog(os.path.join(fixtures, 'catalog-change.pson'))

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.orig.name, 'test123.test')
        self.assertIsInstance(self.orig.resources, dict)

    def test_diff_is_present(self):
        self.assertIsNone(self.orig.diff_if_present(self.orig))
        diffs = self.orig.diff_if_present(self.change)
        self.assertEqual(diffs['total'], 22)
        self.assertEqual(diffs['only_in_self'], set(['Class[Sslcert]']))
        self.assertEqual(diffs['only_in_other'], set(['Class[Sslcert3]']))
        self.assertEqual(len(diffs['resource_diffs']), 2)
        self.assertEqual(diffs['perc_changed'], '18.18%')
