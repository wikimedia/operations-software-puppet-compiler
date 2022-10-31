import tempfile
from pathlib import Path

import mock
from aiounittest import AsyncTestCase
from aiounittest.helpers import futurized

from puppet_compiler import controller, puppet, worker
from puppet_compiler.directories import FHS
from puppet_compiler.utils import FactsFileNotFound


class TestHostWorker(AsyncTestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="puppet-compiler"))
        self.fixtures = Path(__file__).parent.resolve() / "fixtures"
        self.c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet")
        # TODO: there should be an easier way to reset the working dir
        self.c.config.puppet_var = self.fixtures / "puppet_var"
        FHS.setup(19, base)
        self.c.config.base = FHS.base_dir
        self.c.outdir = FHS.output_dir
        self.hw = worker.HostWorker(self.c.config.puppet_var, "test.example.com")

    def test_initialize(self):

        self.assertEqual(self.hw.hostname, "test.example.com")
        self.assertCountEqual(["prod", "change"], self.hw._envs)
        self.assertIsNone(self.hw.diffs)

    @mock.patch("puppet_compiler.directories.Path.is_file")
    def test_facts_file(self, is_file_mock):
        fact_file = self.c.config.puppet_var / "yaml" / "facts" / "test.example.com.yaml"
        self.assertEqual(self.hw.facts_file(), fact_file)
        is_file_mock.return_value = False
        self.hw.facts_file = mock.Mock()
        self.hw.facts_file.side_effect = FactsFileNotFound

    @mock.patch("puppet_compiler.puppet.compile")
    async def test_compile_all(self, compile_mock):
        # Verify simple calls
        err = await self.hw._compile_all()
        calls = [
            mock.call("test.example.com", "prod", self.c.config.puppet_var, None),
            mock.call("test.example.com", "change", self.c.config.puppet_var, None),
        ]
        compile_mock.assert_has_calls(calls)
        self.assertEqual(err, (False, False))

        # Verify all compilation is wrong
        compile_mock.reset_mock()
        compile_mock.side_effect = puppet.CompilationFailedError(command=["dummy", "command"], return_code=30)
        base_error, change_error = await self.hw._compile_all()
        self.assertEqual(base_error, True)
        self.assertEqual(change_error, True)

        # Verify only the change is wrong
        async def complicated_side_effect(*args, **kwdargs):
            if "prod" in args:
                return True
            else:
                raise puppet.CompilationFailedError(command=["dummy", "command"], return_code=30)

        compile_mock.reset_mock()
        compile_mock.side_effect = complicated_side_effect
        base_error, change_error = await self.hw._compile_all()
        self.assertEqual(base_error, False)
        self.assertEqual(change_error, True)

    @mock.patch("puppet_compiler.worker.PuppetCatalog")
    def test_make_diff(self, puppetcatalog_mock):
        instance_mock = puppetcatalog_mock.return_value
        instance_mock.diff_if_present.return_value = None
        self.assertIsNone(self.hw._make_diff())
        self.assertIsNone(self.hw.diffs)

        puppetcatalog_mock.assert_has_calls(
            [
                mock.call(self.c.config.base / "production/catalogs/test.example.com.pson"),
                mock.call(self.c.config.base / "change/catalogs/test.example.com.pson"),
            ]
        )
        instance_mock.diff_if_present.return_value = {"foo": "bar"}
        self.assertTrue(self.hw._make_diff())
        self.assertEqual(self.hw.diffs, {"foo": "bar"})
        instance_mock.diff_if_present.side_effect = ValueError("ehehe")
        self.assertFalse(self.hw._make_diff())

    @mock.patch("puppet_compiler.directories.HostFiles")
    @mock.patch("puppet_compiler.directories.Path.is_file")
    @mock.patch("puppet_compiler.directories.Path.mkdir")
    @mock.patch("shutil.copy")
    def test_make_output(self, mock_copy, mkdir_mock, is_file_mock, host_files_mock):
        is_file_mock.return_value = False
        source = self.c.config.base / "change/catalogs/test.example.com.err"
        dest = self.c.outdir / "test.example.com" / "change.test.example.com.err"
        host_files_mock.return_value.file_for.return_value = source
        host_files_mock.return_value.outfile_for.return_value = dest
        self.hw._make_output()
        mkdir_mock.assert_called_with(mode=0o755, parents=True)
        assert not mock_copy.called
        is_file_mock.return_value = True
        self.hw._make_output()
        mock_copy.assert_called_with(source, dest)

    @mock.patch("puppet_compiler.utils.refresh_yaml_date")
    async def test_run_host(self, mocked_refresh_yaml_date: mock.Mock):
        self.hw.facts_file = mock.Mock(return_value=False)
        self.assertEqual(
            await self.hw.run_host(), worker.RunHostResult(base_error=True, change_error=True, has_diff=None)
        )
        fname = self.fixtures / "puppet_var" / "yaml" / "facts" / "test.eqiad.wmnet"
        self.hw.facts_file.return_value = fname
        self.hw._compile_all = mock.Mock(return_value=futurized((False, False)))
        self.hw._make_diff = mock.Mock(return_value=True)
        self.hw._make_output = mock.Mock(return_value=None)
        self.hw._build_html = mock.Mock(return_value=None)
        self.assertEqual(
            await self.hw.run_host(), worker.RunHostResult(base_error=False, change_error=False, has_diff=True)
        )
        assert mocked_refresh_yaml_date.called
        assert self.hw.facts_file.called
        assert self.hw._compile_all.called
        assert self.hw._make_diff.called
        assert self.hw._make_output.called
        assert self.hw._build_html.called

        self.hw._make_diff.reset_mock()
        self.hw._compile_all.return_value = futurized((True, False))
        self.assertEqual(
            await self.hw.run_host(), worker.RunHostResult(base_error=True, change_error=False, has_diff=None)
        )
        assert not self.hw._make_diff.called

        # An exception writing the output doesn't make the payload fail
        self.hw._make_output.side_effect = Exception("Boom!")
        self.assertEqual(
            await self.hw.run_host(), worker.RunHostResult(base_error=True, change_error=False, has_diff=None)
        )
