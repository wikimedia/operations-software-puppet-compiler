import os
from asyncio import subprocess
from pathlib import Path

from aiounittest import AsyncTestCase
from aiounittest.helpers import futurized
from mock import Mock, call, mock_open, patch

from puppet_compiler import puppet
from puppet_compiler.directories import FHS


class TestPuppetCalls(AsyncTestCase):
    def setUp(self):
        subprocess.create_subprocess_shell = Mock()
        proc_mock = Mock()
        proc_mock.wait.return_value = futurized(Mock())
        proc_mock.returncode = 0
        subprocess.create_subprocess_shell.return_value = futurized(proc_mock)
        self.fixtures = Path(__file__).resolve().parent / "fixtures"
        FHS.setup(10, self.fixtures)
        modulepaths = ["/private/modules", "/src/modules", "/src/vendor_modules"]
        self.modulepath_prod = ":".join([f"{FHS.prod_dir}{d}" for d in modulepaths])
        self.modulepath_change = ":".join([f"{FHS.change_dir}{d}" for d in modulepaths])

    @patch("puppet_compiler.puppet.SpooledTemporaryFile")
    @patch("puppet_compiler.utils.facts_file")
    async def test_compile(self, facts_file_mock, tf_mocker):
        facts_file = Path("/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml")
        facts_file_mock.return_value = facts_file
        os.environ.copy = Mock(return_value={"myenv": "ishere!"})
        env = os.environ.copy()
        env["RUBYLIB"] = FHS.prod_dir / "src/modules/wmflib/lib/"
        m = mock_open(read_data="wat")
        with patch("puppet_compiler.directories.Path.open", m, True) as mocker:
            await puppet.compile("test.codfw.wmnet", "prod", self.fixtures / "puppet_var")

        spool = tf_mocker.return_value
        spool.return_value = ["Test ", "Info: meh"]
        subprocess.create_subprocess_shell.assert_called_with(
            " ".join(
                [
                    "puppet",
                    "master",
                    f"--vardir={self.fixtures / 'puppet_var'}",
                    f"--modulepath={self.modulepath_prod}",
                    f"--confdir={FHS.prod_dir / 'src'}",
                    "--compile=test.codfw.wmnet",
                    "--color=false",
                    "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                    "--factpath=/var/lib/catalog-differ/puppet/yaml/facts",
                    f"--manifest={FHS.prod_dir / 'src'}/manifests",
                    f"--environmentpath={FHS.prod_dir / 'src'}/environments",
                ]
            ),
            env=env,
            stdout=spool,
            stderr=mocker.return_value,
        )
        calls = [call("wb"), call("w")]
        mocker.assert_has_calls(calls, any_order=True)
        with patch("puppet_compiler.directories.Path.open", m, True) as mocker:
            await puppet.compile("test.codfw.wmnet", "test", self.fixtures / "puppet_var")
        subprocess.create_subprocess_shell.assert_called_with(
            " ".join(
                [
                    "puppet",
                    "master",
                    f"--vardir={self.fixtures / 'puppet_var'}",
                    f"--modulepath={self.modulepath_change}",
                    f"--confdir={FHS.change_dir / 'src'}",
                    "--compile=test.codfw.wmnet",
                    "--color=false",
                    "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                    "--factpath=/var/lib/catalog-differ/puppet/yaml/facts",
                    f"--manifest={FHS.change_dir / 'src'}/manifests",
                    f"--environmentpath={FHS.change_dir / 'src'}/environments",
                ]
            ),
            env=env,
            stdout=tf_mocker.return_value,
            stderr=mocker.return_value,
        )
        calls = [call("wb"), call("w")]
        mocker.assert_has_calls(calls, any_order=True)

    @patch("puppet_compiler.puppet.SpooledTemporaryFile")
    @patch("puppet_compiler.utils.facts_file")
    async def test_extra_args_compile(self, facts_file_mock, spooledtemporaryfile_mock):
        facts_file = Path("/var/lib/catalog-differ/puppet/yaml/facts/test.example.com.yaml")
        facts_file_mock.return_value = facts_file
        os.environ.copy = Mock(return_value={"myenv": "ishere!"})
        env = os.environ.copy()
        env["RUBYLIB"] = FHS.prod_dir / "src/modules/wmflib/lib/"
        m = mock_open(read_data="wat")
        with patch("puppet_compiler.directories.Path.open", m, True) as open_mock:
            await puppet.compile("test.codfw.wmnet", "prod", self.fixtures / "puppet_var", None, "--dummy")
        subprocess.create_subprocess_shell.assert_called_with(
            " ".join(
                [
                    "puppet",
                    "master",
                    f"--vardir={self.fixtures / 'puppet_var'}",
                    f"--modulepath={self.modulepath_prod}",
                    f"--confdir={FHS.prod_dir / 'src'}",
                    "--compile=test.codfw.wmnet",
                    "--color=false",
                    "--yamldir=/var/lib/catalog-differ/puppet/yaml",
                    "--factpath=/var/lib/catalog-differ/puppet/yaml/facts",
                    f"--manifest={FHS.prod_dir / 'src'}/manifests",
                    f"--environmentpath={FHS.prod_dir / 'src'}/environments",
                    "--dummy",
                ]
            ),
            env=env,
            stdout=spooledtemporaryfile_mock.return_value,
            stderr=open_mock.return_value,
        )
        calls = [call("wb"), call("w")]
        open_mock.assert_has_calls(calls, any_order=True)
