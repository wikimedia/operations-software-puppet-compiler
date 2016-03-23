import mock
import os
import unittest
import tempfile
import shutil
from puppet_compiler import prepare


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

    def setUp(self):
        fixtures = os.path.join(os.path.dirname(__file__), 'fixtures', 'puppet_var')
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

    def test_copy_hiera(self):
        """Check the hiera file gets copied"""
        with prepare.pushd(os.path.join(os.path.dirname(__file__), 'fixtures')):
            self.m._copy_hiera(self.base)
            with open('hiera.yaml') as f:
                data = f.readlines()
            os.unlink('hiera.yaml')
        self.assertIn(os.path.join(self.base, 'src', 'hieradata'), data[0])
        self.assertIn(os.path.join(self.base, 'private'), data[1])

    @mock.patch('subprocess.call')
    def test_fetch_change(self, mocker):
        """The change can be downloaded"""
        self.m._fetch_change()
        calls = [
            mock.call(['git', 'fetch', '-q', 'https://gerrit.wikimedia.org/r/operations/puppet', 'refs/changes/50/227450/1']),
            mock.call(['git', 'checkout', 'FETCH_HEAD']),
            mock.call(['git', 'pull', '--rebase', 'origin', 'production']),
            mock.call(['git', 'submodule', 'update', '--init'])
        ]
        mocker.assert_has_calls(calls)

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
        exim_priv = os.path.join(self.m.prod_dir, 'private/modules/privateexim')
        exim_pub = os.path.join(self.m.prod_dir, 'src/modules/privateexim')
        mock_symlink.assert_any_call(exim_priv, exim_pub)
