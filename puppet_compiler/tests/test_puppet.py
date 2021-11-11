import os
import subprocess
import unittest
from pathlib import Path

import mock

from puppet_compiler import puppet
from puppet_compiler.directories import FHS


class TestPuppetCalls(unittest.TestCase):
    def setUp(self):
        subprocess.check_call = mock.Mock()
        self.fixtures = Path(__file__).resolve().parent / "fixtures"
        FHS.setup(10, self.fixtures)

    @mock.patch("puppet_compiler.puppet.SpooledTemporaryFile")
    @mock.patch("puppet_compiler.utils.facts_file")
    def test_compile(self, facts_file_mock, tf_mocker):
        facts_file = Path("/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml")
        facts_file_mock.return_value = facts_file
        os.environ.copy = mock.Mock(return_value={"myenv": "ishere!"})
        env = os.environ.copy()
        env["RUBYLIB"] = FHS.prod_dir / "src/modules/wmflib/lib/"
        m = mock.mock_open(read_data="wat")
        with mock.patch("puppet_compiler.directories.Path.open", m, True) as mocker:
            puppet.compile("test.codfw.wmnet", "prod", self.fixtures / "puppet_var")

        spool = tf_mocker.return_value
        spool.return_value = ["Test ", "Info: meh"]
        subprocess.check_call.assert_called_with(
            [
                "puppet",
                "master",
                "--vardir=%s" % (self.fixtures / "puppet_var"),
                "--modulepath=%(basedir)s/private/modules:" "%(basedir)s/src/modules" % {"basedir": FHS.prod_dir},
                "--confdir=%s" % (FHS.prod_dir / "src"),
                "--compile=test.codfw.wmnet",
                "--color=false",
                "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                "--manifest=%s/manifests" % (FHS.prod_dir / "src"),
                "--environmentpath=%s/environments" % (FHS.prod_dir / "src"),
            ],
            env=env,
            stdout=spool,
            stderr=mocker.return_value,
        )
        calls = [mock.call("wb"), mock.call("w")]
        mocker.assert_has_calls(calls, any_order=True)
        with mock.patch("puppet_compiler.directories.Path.open", m, True) as mocker:
            puppet.compile("test.codfw.wmnet", "test", self.fixtures / "puppet_var")
        subprocess.check_call.assert_called_with(
            [
                "puppet",
                "master",
                "--vardir=%s" % (self.fixtures / "puppet_var"),
                "--modulepath=%(basedir)s/private/modules:" "%(basedir)s/src/modules" % {"basedir": FHS.change_dir},
                "--confdir=%s" % (FHS.change_dir / "src"),
                "--compile=test.codfw.wmnet",
                "--color=false",
                "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                "--manifest=%s/manifests" % (FHS.change_dir / "src"),
                "--environmentpath=%s/environments" % (FHS.change_dir / "src"),
            ],
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value,
        )
        calls = [mock.call("wb"), mock.call("w")]
        mocker.assert_has_calls(calls, any_order=True)

    @mock.patch("puppet_compiler.puppet.SpooledTemporaryFile")
    @mock.patch("puppet_compiler.utils.facts_file")
    def test_extra_args_compile(self, facts_file_mock, tf_mocker):
        facts_file = Path("/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml")
        facts_file_mock.return_value = facts_file
        os.environ.copy = mock.Mock(return_value={"myenv": "ishere!"})
        env = os.environ.copy()
        env["RUBYLIB"] = FHS.prod_dir / "src/modules/wmflib/lib/"
        m = mock.mock_open(read_data="wat")
        with mock.patch("puppet_compiler.directories.Path.open", m, True) as mocker:
            puppet.compile("test.codfw.wmnet", "prod", self.fixtures / "puppet_var", None, "--dummy")
        subprocess.check_call.assert_called_with(
            [
                "puppet",
                "master",
                "--vardir=%s" % (self.fixtures / "puppet_var"),
                "--modulepath=%(basedir)s/private/modules:" "%(basedir)s/src/modules" % {"basedir": FHS.prod_dir},
                "--confdir=%s" % (FHS.prod_dir / "src"),
                "--compile=test.codfw.wmnet",
                "--color=false",
                "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                "--manifest=%s/manifests" % (FHS.prod_dir / "src"),
                "--environmentpath=%s/environments" % (FHS.prod_dir / "src"),
                "--dummy",
            ],
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value,
        )
        calls = [mock.call("wb"), mock.call("w")]
        mocker.assert_has_calls(calls, any_order=True)
