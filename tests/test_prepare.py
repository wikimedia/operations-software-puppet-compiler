import shutil
import tempfile
import unittest
from pathlib import Path

import mock

from puppet_compiler import prepare
from puppet_compiler.config import ControllerConfig
from puppet_compiler.directories import FHS


class TestGit(unittest.TestCase):
    def setUp(self):
        self.git = prepare.Git()

    @mock.patch("subprocess.check_call")
    def test_call_no_args(self, mocker):
        """Init a git repository"""
        self.git.init()
        mocker.assert_called_with(["git", "init"])

    @mock.patch("subprocess.check_call")
    def test_call_with_args(self, mocker):
        self.git.clone("-q", "/src/orig", "/src/dest")
        mocker.assert_called_with(["git", "clone", "-q", "/src/orig", "/src/dest"])


class TestManageCode(unittest.TestCase):
    """
    Tests the creation of the new git trees
    """

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="puppet-compiler"))
        FHS.setup(19, cls.base)

    def setUp(self):
        self.fixtures = Path(__file__).parent.resolve() / "fixtures"
        config = ControllerConfig(
            base=self.base,
            puppet_src="https://gerrit.wikimedia.org/r/operations/puppet",
            puppet_private="https://gerrit.wikimedia.org/r/labs/private",
            puppet_netbox="https://netbox-exports.wikimedia.org/netbox-hiera",
            puppet_var=self.fixtures / "puppet_var",
        )
        self.m = prepare.ManageCode(config, 19, 227450)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base)

    def _test_copy_hiera(self, realm):
        """Check the hiera file gets copied"""
        with prepare.pushd(self.fixtures):
            self.m._copy_hiera(self.base, realm)
            with open("hiera.yaml") as f:
                data = f.readlines()
            Path("hiera.yaml").unlink()
        self.assertIn(str(self.base / "src" / "hieradata"), data[0])
        self.assertIn(str(self.base / "private"), data[1])
        self.assertIn(realm, data[2])

    def test_copy_hiera(self):
        self._test_copy_hiera("production")
        self._test_copy_hiera("labs")

    @mock.patch("puppet_compiler.prepare.LDAP_YAML_PATH", "ldap.yaml")
    def test_create_puppetconf(self):
        fn = Path("puppet.conf")
        with prepare.pushd(self.fixtures):
            if fn.is_file():
                fn.unlink()
            self.m._create_puppetconf(self, "production")
            self.assertFalse(fn.is_file())

            self.m._create_puppetconf(self, "labs")
            data = fn.read_text()
            fn.unlink()
        self.assertIn("node_terminus = exec", data)

    @mock.patch("subprocess.check_call")
    def test_fetch_change(self, mocker):
        """The change can be downloaded"""
        self.m._fetch_change()
        calls = [
            mock.call(
                ["git", "fetch", "-q", "https://gerrit.wikimedia.org/r/operations/puppet", "refs/changes/50/227450/1"]
            ),
            mock.call(["git", "checkout", "FETCH_HEAD"]),
            mock.call(["git", "pull", "--rebase", "origin", "production"]),
        ]
        mocker.assert_has_calls(calls)
        # Now test a change to another repository
        self.m.change_id = 363216
        self.assertRaises(RuntimeError, self.m._fetch_change)

    @mock.patch("puppet_compiler.prepare.Path.symlink_to")
    @mock.patch("shutil.copytree")
    def test_prepare_dir(self, mock_copy, mock_symlink_to):
        """Changes get properly prepared"""
        # pushd support

        (self.base / "19" / "production" / "src").mkdir(parents=True)
        self.m.git = mock.MagicMock()
        self.m._prepare_dir(self.m.prod_dir)
        prod_src = self.m.prod_dir / "src"
        self.m.git.clone.assert_any_call("-q", "https://gerrit.wikimedia.org/r/operations/puppet", str(prod_src))
        assert 3 == self.m.git.clone.call_count
        mock_copy.assert_called_with(self.m.puppet_var / "ssl", prod_src / "ssl")
        assert 3 == mock_symlink_to.call_count
        exim_priv = self.m.prod_dir / "private/modules/privateexim"
        mock_symlink_to.assert_any_call(exim_priv)

    @mock.patch("puppet_compiler.prepare.pushd")
    def test_refresh(self, pushd):
        self.m.git = mock.MagicMock()
        self.m.refresh("/__test")
        pushd.assert_called_with("/__test")
        self.m.git.pull.assert_called_with("-q", "--rebase")

    @mock.patch("puppet_compiler.prepare.pushd")
    def test_prepare(self, pushd):
        self.m._prepare_dir = mock.MagicMock()
        self.m._fetch_change = mock.MagicMock()
        self.m._copy_hiera = mock.MagicMock()
        self.m._create_puppetconf = mock.MagicMock()
        self.m.prepare()
        for dirname in self.m.base_dir, self.m.prod_dir, self.m.change_dir:
            assert dirname.is_dir()
        self.m._prepare_dir.assert_has_calls(
            [mock.call(self.m.prod_dir)],
            [mock.call(self.m.change_dir)],
        )
        assert self.m._fetch_change.called
