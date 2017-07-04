import unittest

from puppet_compiler.directories import FHS, HostFiles


class TestHostFiles(unittest.TestCase):

    def setUp(self):
        FHS.setup(19, '/mnt/jenkins-workspace')
        self.hostfiles = HostFiles('test.example.com')

    def test_outdir(self):
        self.assertEqual(self.hostfiles.outdir, '/mnt/jenkins-workspace/output/19/test.example.com')

    def test_file_for(self):
        self.assertEqual(
            self.hostfiles.file_for('prod', 'catalog'),
            '/mnt/jenkins-workspace/19/production/catalogs/test.example.com.pson'
        )
        self.assertEqual(
            self.hostfiles.file_for('prod', 'errors'),
            '/mnt/jenkins-workspace/19/production/catalogs/test.example.com.err'
        )
        self.assertEqual(
            self.hostfiles.file_for('change', 'catalog'),
            '/mnt/jenkins-workspace/19/change/catalogs/test.example.com.pson'
        )
        self.assertEqual(
            self.hostfiles.file_for('future', 'catalog'),
            '/mnt/jenkins-workspace/19/change/catalogs/test.example.com-future.pson'
        )
        self.assertEqual(
            self.hostfiles.file_for('change', 'diff'),
            '/mnt/jenkins-workspace/19/diffs/test.example.com.diff'
        )
        self.assertEqual(
            self.hostfiles.file_for('test', 'diff'),
            '/mnt/jenkins-workspace/19/diffs/test.example.com-test.diff'
        )
        # Now something we don't have
        self.assertRaises(ValueError, self.hostfiles.file_for, 'test', 'none')
