import os
import shutil
import tempfile
import unittest

from puppet_compiler.differ import PuppetCatalog
from puppet_compiler.directories import FHS, HostFiles
from puppet_compiler.presentation import html


class TestHost(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="puppet-compiler")
        fixtures = os.path.join(os.path.dirname(__file__), "fixtures")
        orig = PuppetCatalog(os.path.join(fixtures, "catalog.pson"))
        change = PuppetCatalog(os.path.join(fixtures, "catalog-change.pson"))
        self.diffs = orig.diff_if_present(change)
        FHS.setup("10", self.tempdir)
        self.files = HostFiles("test.example.com")
        os.makedirs(self.files.outdir)

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
        output = os.path.join(h.outdir, h.page_name)
        assert os.path.isfile(output)
        with open(output, "r") as fh:
            html_data = fh.read()
        assert len(html_data) > 0
