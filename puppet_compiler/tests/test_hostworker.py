import unittest
import mock
import os
from puppet_compiler import controller, worker
import subprocess


class TestHostWorker(unittest.TestCase):

    def setUp(self):
        self.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        self.c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        self.hw = worker.HostWorker(self.c.config['puppet_var'],
                                    'test.example.com')

    def test_initialize(self):

        self.assertEquals(self.hw.hostname, 'test.example.com')
        self.assertItemsEqual(['prod', 'change'], self.hw._envs)
        self.assertIsNone(self.hw.diffs)
        self.assertEqual(self.hw.resource_filter, worker.future_filter)

    @mock.patch('os.path.isfile')
    def test_facts_file(self, isfile):
        isfile.return_value = True
        self.assertEqual(
            self.hw.facts_file(),
            '/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml')
        isfile.return_value = False
        self.assertIsNone(self.hw.facts_file())

    @mock.patch('puppet_compiler.puppet.compile')
    def test_compile_all(self, mocker):
        # Verify simple calls
        err = self.hw._compile_all()
        calls = [
            mock.call('test.example.com', 'prod',
                      '/var/lib/catalog-differ/puppet'),
            mock.call('test.example.com', 'change',
                      '/var/lib/catalog-differ/puppet'),
        ]
        mocker.assert_has_calls(calls)
        self.assertEquals(err, 0)

        # Verify all compilation is wrong
        mocker.reset_mock()
        mocker.side_effect = subprocess.CalledProcessError(cmd="ehehe",
                                                           returncode=30)
        err = self.hw._compile_all()
        self.assertEquals(err, 3)

        # Verify only the change is wrong
        def complicated_side_effect(*args, **kwdargs):
            if 'prod' in args:
                return True
            else:
                raise subprocess.CalledProcessError(cmd="ehehe", returncode=30)
        mocker.reset_mock()
        mocker.side_effect = complicated_side_effect
        err = self.hw._compile_all()
        self.assertEquals(err, 2)

    @mock.patch('puppet_compiler.worker.PuppetCatalog')
    def test_make_diff(self, mocker):
        instance_mock = mocker.return_value
        instance_mock.diff_if_present.return_value = None
        self.assertIsNone(self.hw._make_diff())
        self.assertIsNone(self.hw.diffs)

        mocker.assert_has_calls(
            [
                mock.call(
                    '/mnt/jenkins-workspace/19/production/catalogs/test.example.com.pson', worker.future_filter
                ),
                mock.call(
                    '/mnt/jenkins-workspace/19/change/catalogs/test.example.com.pson', worker.future_filter
                )
            ]
        )
        instance_mock.diff_if_present.return_value = {'foo': 'bar'}
        self.assertTrue(self.hw._make_diff())
        self.assertEqual(self.hw.diffs, {'foo': 'bar'})
        instance_mock.diff_if_present.side_effect = ValueError("ehehe")
        self.assertFalse(self.hw._make_diff())

    @mock.patch('os.path.isfile')
    @mock.patch('os.makedirs')
    @mock.patch('shutil.copy')
    def test_make_output(self, mock_copy, mock_makedirs, mock_isfile):
        mock_isfile.return_value = False
        self.hw._make_output()
        mock_makedirs.assert_called_with(self.hw._files.outdir, 0755)
        assert not mock_copy.called
        mock_isfile.return_value = True
        self.hw._make_output()
        mock_copy.assert_called_with(
            '/mnt/jenkins-workspace/19/change/catalogs/test.example.com.err',
            '/mnt/jenkins-workspace/output/19/test.example.com/change.test.example.com.err',
        )

    def test_run_host(self):
        self.hw.facts_file = mock.Mock(return_value=False)
        self.assertEquals(self.hw.run_host(), (True, True, None))
        fname = os.path.join(self.fixtures, 'puppet_var', 'yaml',
                             'facts', 'test.eqiad.wmnet')
        self.hw.facts_file.return_value = fname
        self.hw._compile_all = mock.Mock(return_value=0)
        self.hw._make_diff = mock.Mock(return_value=True)
        self.hw._make_output = mock.Mock(return_value=None)
        self.hw._build_html = mock.Mock(return_value=None)
        self.assertEquals(self.hw.run_host(), (False, False, True))
        assert self.hw.facts_file.called
        assert self.hw._compile_all.called
        assert self.hw._make_diff.called
        assert self.hw._make_output.called
        assert self.hw._build_html.called

        self.hw._compile_all.return_value = 1
        self.hw._make_diff.reset_mock()
        self.assertEquals(self.hw.run_host(), (True, False, None))
        assert not self.hw._make_diff.called
        # An exception writing the output doesn't make the payload fail
        self.hw._make_output.side_effect = Exception('Boom!')
        self.assertEquals(self.hw.run_host(), (True, False, None))


class TestFutureHostWorker(unittest.TestCase):
    def setUp(self):
        self.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        self.hw = worker.FutureHostWorker(c.config['puppet_var'],
                                          'test.example.com')

    def test_initialize(self):
        self.assertListEqual(self.hw._envs, ['change', 'future'])

    def test_compile_all(self):
        self.hw._compile = mock.Mock(return_value=True)
        self.assertEquals(self.hw._compile_all(), 0)
        future_parser = [
            '--environment=future',
            '--parser=future',
            '--environmentpath=/mnt/jenkins-workspace/19/change/src/environments',
            '--default_manifest=\$confdir/manifests/site.pp'
        ]
        self.hw._compile.assert_has_calls([
            mock.call('change', []),
            mock.call('future', future_parser)
        ])
