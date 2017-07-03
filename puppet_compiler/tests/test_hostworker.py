import unittest
import mock
import os
from puppet_compiler import controller, worker
import subprocess


class TestHostWorker(unittest.TestCase):

    def setUp(self):
        self.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        self.c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        self.m = self.c.m
        self.hw = worker.HostWorker(self.m,
                                    'test.codfw.wmnet', '/what/you/want')

    def test_initialize(self):

        self.assertEquals(self.hw.hostname, 'test.codfw.wmnet')
        self.assertItemsEqual(['prod', 'change'], self.hw.files.keys())
        self.assertEquals(
            '/mnt/jenkins-workspace/19/change/catalogs/test.codfw.wmnet.err',
            self.hw.files['change']['errors']
        )
        self.assertEquals(
            '/mnt/jenkins-workspace/19/production/catalogs/test.codfw.wmnet.pson',
            self.hw.files['prod']['catalog']
        )
        self.assertEquals('/what/you/want/test.codfw.wmnet',
                          self.hw.outdir)

    @mock.patch('puppet_compiler.puppet.compile')
    def test_compile_all(self, mocker):
        # Verify simple calls
        err = self.hw._compile_all()
        calls = [
            mock.call('test.codfw.wmnet', '/mnt/jenkins-workspace/19/production',
                      '/var/lib/catalog-differ/puppet'),
            mock.call('test.codfw.wmnet', '/mnt/jenkins-workspace/19/change',
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
            if '/mnt/jenkins-workspace/19/production' in args:
                return True
            else:
                raise subprocess.CalledProcessError(cmd="ehehe", returncode=30)
        mocker.reset_mock()
        mocker.side_effect = complicated_side_effect
        err = self.hw._compile_all()
        self.assertEquals(err, 2)

    @mock.patch('puppet_compiler.puppet.diff')
    def test_make_diff(self, mocker):
        mocker.return_value = True
        self.hw._get_diff = mock.Mock(return_value=True)
        retval = self.hw._make_diff(0)
        mocker.assert_called_with('/mnt/jenkins-workspace/19', 'test.codfw.wmnet')
        self.assertEquals(retval, 'diff')
        self.hw._get_diff = mock.Mock(return_value=False)
        self.assertEquals(self.hw._make_diff(0), 'noop')
        mocker.reset_mock()
        self.assertEquals(self.hw._make_diff(1), 'noop')
        assert not mocker.called
        mocker.reset_mock()
        self.assertEquals(self.hw._make_diff(2), 'err')
        assert not mocker.called
        mocker.side_effect = subprocess.CalledProcessError(cmd="ehehe", returncode=30)
        self.assertEquals(self.hw._make_diff(0), 'fail')
        self.assertEquals(self.hw._make_diff(3), 'fail')

    @mock.patch('os.path.isfile')
    @mock.patch('os.makedirs')
    @mock.patch('shutil.copy')
    def test_make_output(self, mock_copy, mock_makedirs, mock_isfile):
        mock_isfile.return_value = False
        self.hw._make_output()
        mock_makedirs.assert_called_with('/what/you/want/test.codfw.wmnet', 0755)
        assert not mock_copy.called
        mock_isfile.return_value = True
        mock_copy.assert_called_any(
            '/mnt/jenkins-workspace/19/production/catalogs/test.codfw.wmnet.pson',
            '/what/you/want/test.codfw.wmnet/production.test.codfw.wmnet.pson',
        )

    @mock.patch('os.path')
    def test_get_diff(self, mock_path):
        mock_path.join.return_value = self.fixtures + '/' + 'exit_nodiff'
        mock_path.isfile.return_value = True
        mock_path.getsize.return_value = 100
        self.assertEquals(self.hw._get_diff(), False)
        filename = self.fixtures + '/' + 'exit_diff'
        mock_path.join.return_value = filename
        self.assertEquals(self.hw._get_diff(), filename)

    def test_build_html(self):
        pass

    def test_run_host(self):
        self.hw.m.find_yaml = mock.Mock(return_value=False)
        self.assertEquals(self.hw.run_host(), 'fail')
        self.hw.m.find_yaml = mock.Mock(return_value=True)
        self.hw._compile_all = mock.Mock(return_value=0)
        self.hw._make_diff = mock.Mock(return_value='diff')
        self.hw._make_output = mock.Mock(return_value=None)
        self.hw._build_html = mock.Mock(return_value=None)
        self.assertEquals(self.hw.run_host(), 'diff')
        assert self.hw.m.find_yaml.called
        assert self.hw._compile_all.called
        self.hw._make_diff.assert_called_with(0)
        assert self.hw._make_output.called
        assert self.hw._build_html.called
