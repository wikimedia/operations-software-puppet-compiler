import mock
import os
import unittest
import tempfile
import shutil
from puppet_compiler import prepare
from puppet_compiler.directories import FHS


class TestGit(unittest.TestCase):

    def setUp(self):
        self.git = prepare.Git()

    @mock.patch('subprocess.call')
    def test_call_no_args(self, mocker):
        """Init a git repository"""
        self.git.init()
        mocker.assert_called_with(['git', 'init'])

    @mock.patch('subprocess.call')
    def test_call_with_args(self, mocker):
        self.git.clone('-q', '/src/orig', '/src/dest')
        mocker.assert_called_with(['git', 'clone', '-q',
                                   '/src/orig', '/src/dest'])


class TestManageCode(unittest.TestCase):
    """
    Tests the creation of the new git trees
    """

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix='puppet-compiler')
        FHS.setup(19, cls.base)

    def setUp(self):
        fixtures = os.path.join(os.path.dirname(__file__),
                                'fixtures', 'puppet_var')
        self.m = prepare.ManageCode(
            {'base': self.base,
             'puppet_src': 'https://gerrit.wikimedia.org/r/operations/puppet',
             'puppet_private': 'https://gerrit.wikimedia.org/r/labs/private',
             'puppet_var': fixtures},
            19,
            227450)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base)

    def _test_copy_hiera(self, realm):
        """Check the hiera file gets copied"""
        with prepare.pushd(os.path.join(os.path.dirname(__file__),
                                        'fixtures')):
            self.m._copy_hiera(self.base, realm)
            with open('hiera.yaml') as f:
                data = f.readlines()
            os.unlink('hiera.yaml')
        self.assertIn(os.path.join(self.base, 'src', 'hieradata'), data[0])
        self.assertIn(os.path.join(self.base, 'private'), data[1])
        self.assertIn(realm, data[2])

    def test_copy_hiera(self):
        self._test_copy_hiera('production')
        self._test_copy_hiera('labs')

    @mock.patch('puppet_compiler.prepare.LDAP_YAML_PATH', 'ldap.yaml')
    def test_create_puppetconf(self):
        fn = 'puppet.conf'
        with prepare.pushd(os.path.join(os.path.dirname(__file__),
                                        'fixtures')):
            if os.path.isfile(fn):
                os.unlink(fn)
            self.m._create_puppetconf(self, 'production')
            self.assertFalse(os.path.isfile(fn))

            self.m._create_puppetconf(self, 'labs')
            with open(fn) as f:
                data = f.read()
            os.unlink(fn)
        self.assertIn('ldapuser = cn=proxyagent', data)
        self.assertIn('password = not_the_password', data)

    @mock.patch('subprocess.call')
    def test_fetch_change(self, mocker):
        """The change can be downloaded"""
        self.m._fetch_change()
        calls = [
            mock.call(['git', 'fetch', '-q',
                       'https://gerrit.wikimedia.org/r/operations/puppet',
                       'refs/changes/50/227450/1']),
            mock.call(['git', 'checkout', 'FETCH_HEAD']),
            mock.call(['git', 'pull', '--rebase', 'origin', 'production']),
            mock.call(['git', 'submodule', 'update', '--init'])
        ]
        mocker.assert_has_calls(calls)
        # Now test a change to another repository
        self.m.change_id = 363216
        self.assertRaises(RuntimeError, self.m._fetch_change)

    @mock.patch('subprocess.call')
    @mock.patch('os.chdir', return_value=None)
    def test_fetch_change_submodule(self, os_chdir_mocker, subprocess_mocker):
        """The submodule change can be downloaded"""
        self.m.change_id = 280690
        self.m._fetch_change()
        subprocess_calls = [
            mock.call(['git', 'fetch', '-q',
                       'https://gerrit.wikimedia.org/r/operations'
                       '/puppet/varnishkafka',
                       'refs/changes/90/280690/1']),
            mock.call(['git', 'checkout', 'FETCH_HEAD'])
        ]
        subprocess_mocker.assert_has_calls(subprocess_calls)

        # Checking that os.path.exists and os.chdir are called with
        # the correct submodule dir.
        submodule_dir = os.path.join(os.getcwd(), 'modules', 'varnishkafka')
        os_chdir_calls = mock.call(submodule_dir)
        assert os_chdir_calls in os_chdir_mocker.mock_calls

    @mock.patch('os.symlink')
    @mock.patch('shutil.copytree')
    def test_prepare_dir(self, mock_copy, mock_symlink):
        """Changes get properly prepared"""
        # pushd support
        os.makedirs(os.path.join(self.base, '19', 'production', 'src'))
        self.m.git = mock.MagicMock()
        self.m._prepare_dir(self.m.prod_dir)
        prod_src = os.path.join(self.m.prod_dir, 'src')
        self.m.git.clone.assert_any_call(
            '-q',
            'https://gerrit.wikimedia.org/r/operations/puppet',
            prod_src)
        assert 2 == self.m.git.clone.call_count
        assert 2 == self.m.git.submodule.call_count
        mock_copy.assert_called_with(self.m.puppet_var + '/ssl',
                                     prod_src + '/ssl')
        assert 3 == mock_symlink.call_count
        exim_priv = os.path.join(self.m.prod_dir,
                                 'private/modules/privateexim')
        exim_pub = os.path.join(self.m.prod_dir,
                                'src/modules/privateexim')
        mock_symlink.assert_any_call(exim_priv, exim_pub)

    @mock.patch('puppet_compiler.prepare.pushd')
    def test_refresh(self, pushd):
        self.m.git = mock.MagicMock()
        self.m.refresh('/__test')
        pushd.assert_called_with('/__test')
        self.m.git.pull.assert_called_with('-q', '--rebase')

    @mock.patch('puppet_compiler.prepare.pushd')
    def test_prepare(self, pushd):
        self.m._prepare_dir = mock.MagicMock()
        self.m._fetch_change = mock.MagicMock()
        self.m._copy_hiera = mock.MagicMock()
        self.m._create_puppetconf = mock.MagicMock()
        self.m.prepare()
        for dirname in self.m.base_dir, self.m.prod_dir, self.m.change_dir:
            assert os.path.isdir(dirname)
        self.m._prepare_dir.assert_has_calls(
            [mock.call(self.m.prod_dir)],
            [mock.call(self.m.change_dir)],
        )
        assert self.m._fetch_change.called
