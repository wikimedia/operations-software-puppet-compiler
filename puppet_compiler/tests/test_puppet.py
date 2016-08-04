import unittest
import mock
import subprocess
import os
from puppet_compiler import puppet


class TestPuppetCalls(unittest.TestCase):

    def setUp(self):
        subprocess.check_call = mock.Mock()
        self.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')

    @mock.patch('puppet_compiler.puppet.spoolfile')
    def test_compile(self, tf_mocker):
        os.environ.copy = mock.Mock(return_value={'myenv': 'ishere!'})
        env = os.environ.copy()
        env['RUBYLIB'] = self.fixtures + '/src/modules/wmflib/lib/'
        m = mock.mock_open(read_data='wat')
        with mock.patch('__builtin__.open', m, True) as mocker:
            puppet.compile('test.codfw.wmnet', self.fixtures, self.fixtures + '/puppet_var')
        subprocess.check_call.assert_called_with(
            ['puppet',
             'master',
             '--vardir=%s' % self.fixtures + '/puppet_var',
             '--modulepath=%(basedir)s/private/modules:'
             '%(basedir)s/src/modules' % {'basedir': self.fixtures},
             '--confdir=%s/%s' % (self.fixtures, 'src'),
             '--templatedir=%s/%s' % (self.fixtures, 'src/templates'),
             '--trusted_node_data',
             '--compile=test.codfw.wmnet',
             '--color=false'],
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value
        )
        hostfile = os.path.join(self.fixtures, 'catalogs', 'test.codfw.wmnet')
        calls = [
            mock.call(hostfile + '.pson', 'w'),
            mock.call(hostfile + '.err', 'w'),
        ]
        mocker.assert_has_calls(calls, any_order=True)

    @mock.patch('puppet_compiler.puppet.spoolfile')
    def test_diff(self, tf_mocker):
        m = mock.mock_open(read_data='wat')
        with mock.patch('__builtin__.open', m, True) as mocker:
            puppet.diff(self.fixtures, 'test.codfw.wmnet')
        mocker.assert_called_with(self.fixtures + '/diffs/test.codfw.wmnet.diff', 'w')
        subprocess.check_call.called_with(
            ['puppet',
             'catalog',
             'diff',
             '--show_resource_diff',
             '--content_diff',
             self.fixtures + '/production/catalogs/test.codfw.wmnet.json',
             self.fixtures + '/change/catalogs/test.codfw.wmnet.json'],
            stdout=tf_mocker.return_value
        )
