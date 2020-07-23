import unittest
import mock
import subprocess
import os
from puppet_compiler import puppet
from puppet_compiler.directories import FHS


class TestPuppetCalls(unittest.TestCase):

    def setUp(self):
        os.environ['PUPPET_VERSION'] = '3'
        subprocess.check_call = mock.Mock()
        self.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        FHS.setup(10, self.fixtures)

    @mock.patch('puppet_compiler.puppet.SpooledTemporaryFile')
    @mock.patch('puppet_compiler.utils.facts_file',
                mock.MagicMock(
                    return_value='/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml'))
    def test_compile(self, tf_mocker):
        os.environ.copy = mock.Mock(return_value={'myenv': 'ishere!'})
        env = os.environ.copy()
        env['RUBYLIB'] = FHS.prod_dir + '/src/modules/wmflib/lib/'
        m = mock.mock_open(read_data='wat')
        try:
            # TODO: remove try/except block when python2 is droped
            with mock.patch('__builtin__.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'prod', self.fixtures + '/puppet_var')
        except ImportError:
            with mock.patch('builtins.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'prod', self.fixtures + '/puppet_var')

        spool = tf_mocker.return_value
        spool.return_value = ["Test ", "Info: meh"]
        subprocess.check_call.assert_called_with(
            ['puppet',
             'master',
             '--vardir=%s' % self.fixtures + '/puppet_var',
             '--modulepath=%(basedir)s/private/modules:'
             '%(basedir)s/src/modules' % {'basedir': FHS.prod_dir},
             '--confdir=%s/%s' % (FHS.prod_dir, 'src'),
             '--compile=test.codfw.wmnet',
             '--color=false',
             '--yamldir=/var/lib/catalog-differ/puppet/yaml',
             '--manifest=%s/%s/manifests' % (FHS.prod_dir, 'src'),
             '--environmentpath=%s/%s/environments' % (FHS.prod_dir, 'src'),
             '--trusted_node_data',
             '--parser=future',
             '--environment=future'],
            env=env,
            stdout=spool,
            stderr=mocker.return_value
        )
        hostfile = os.path.join(self.fixtures, '10/production/catalogs', 'test.codfw.wmnet')
        calls = [
            mock.call(hostfile + '.pson', 'w'),
            mock.call(hostfile + '.err', 'w'),
        ]
        mocker.assert_has_calls(calls, any_order=True)
        try:
            # TODO: remove try/except block when python2 is droped
            with mock.patch('__builtin__.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'test', self.fixtures + '/puppet_var')
        except ImportError:
            with mock.patch('builtins.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'test', self.fixtures + '/puppet_var')
        subprocess.check_call.assert_called_with(
            ['puppet',
             'master',
             '--vardir=%s' % self.fixtures + '/puppet_var',
             '--modulepath=%(basedir)s/private/modules:'
             '%(basedir)s/src/modules' % {'basedir': FHS.change_dir},
             '--confdir=%s/%s' % (FHS.change_dir, 'src'),
             '--compile=test.codfw.wmnet',
             '--color=false',
             '--yamldir=/var/lib/catalog-differ/puppet/yaml',
             '--manifest=%s/%s/manifests' % (FHS.change_dir, 'src'),
             '--environmentpath=%s/%s/environments' % (FHS.change_dir, 'src'),
             '--trusted_node_data',
             '--parser=future',
             '--environment=future'],
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value
        )
        hostfile = os.path.join(self.fixtures, '10/change/catalogs', 'test.codfw.wmnet-test')
        calls = [
            mock.call(hostfile + '.pson', 'w'),
            mock.call(hostfile + '.err', 'w'),
        ]
        mocker.assert_has_calls(calls, any_order=True)

    @mock.patch('puppet_compiler.puppet.SpooledTemporaryFile')
    @mock.patch('puppet_compiler.utils.facts_file',
                mock.MagicMock(
                    return_value='/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml'))
    def test_extra_args_compile(self, tf_mocker):
        os.environ.copy = mock.Mock(return_value={'myenv': 'ishere!'})
        env = os.environ.copy()
        env['RUBYLIB'] = FHS.prod_dir + '/src/modules/wmflib/lib/'
        m = mock.mock_open(read_data='wat')
        try:
            # TODO: remove try/except block when python2 is droped
            with mock.patch('__builtin__.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'prod', self.fixtures +
                               '/puppet_var', None, '--dummy')
        except ImportError:
            with mock.patch('builtins.open', m, True) as mocker:
                puppet.compile('test.codfw.wmnet', 'prod', self.fixtures +
                               '/puppet_var', None, '--dummy')
        subprocess.check_call.assert_called_with(
            ['puppet',
             'master',
             '--vardir=%s' % self.fixtures + '/puppet_var',
             '--modulepath=%(basedir)s/private/modules:'
             '%(basedir)s/src/modules' % {'basedir': FHS.prod_dir},
             '--confdir=%s/%s' % (FHS.prod_dir, 'src'),
             '--compile=test.codfw.wmnet',
             '--color=false',
             '--yamldir=/var/lib/catalog-differ/puppet/yaml',
             '--manifest=%s/%s/manifests' % (FHS.prod_dir, 'src'),
             '--environmentpath=%s/%s/environments' % (FHS.prod_dir, 'src'),
             '--trusted_node_data',
             '--parser=future',
             '--environment=future',
             '--dummy'],
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value
        )
        hostfile = os.path.join(self.fixtures, '10/production/catalogs', 'test.codfw.wmnet')
        calls = [
            mock.call(hostfile + '.pson', 'w'),
            mock.call(hostfile + '.err', 'w'),
        ]
        mocker.assert_has_calls(calls, any_order=True)
