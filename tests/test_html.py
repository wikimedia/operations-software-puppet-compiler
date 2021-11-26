import shutil
import tempfile
import unittest
from pathlib import Path

from puppet_compiler.differ import PuppetCatalog
from puppet_compiler.directories import FHS, HostFiles
from puppet_compiler.presentation import html


class TestHost(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="puppet-compiler")
        fixtures = Path(__file__).parent.resolve() / "fixtures"
        orig = PuppetCatalog(fixtures / "catalog.pson")
        change = PuppetCatalog(fixtures / "catalog-change.pson")
        self.diffs = orig.diff_if_present(change)
        FHS.setup("10", self.tempdir)
        self.files = HostFiles("test.example.com")
        self.files.outdir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_init(self):
        h = html.Host("test.example.com", self.files, "diff")
        self.assertEqual(h.retcode, "diff")
        self.assertEqual(h.hostname, "test.example.com")
        self.assertEqual(h.outdir, self.files.outdir)

    def test_htmlpage(self):
        h = html.Host("test.example.com", self.files, "diff")
        h.htmlpage(self.diffs)
        # Test the test file has been produced
        output = h.outdir / h.page_name
        assert output.is_file()
        with open(output, "r") as fh:
            html_data = fh.read()
        assert len(html_data) > 0
