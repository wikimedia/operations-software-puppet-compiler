import unittest
from pathlib import Path

from puppet_compiler.directories import FHS, HostFiles


class TestHostFiles(unittest.TestCase):
    def setUp(self):
        FHS.setup(1, 19, "/mnt/jenkins-workspace")
        self.hostfiles = HostFiles("test.example.com")

    def test_outdir(self):
        self.assertEqual(self.hostfiles.outdir, Path("/mnt/jenkins-workspace/output/1/19/test.example.com"))

    def test_file_for(self):
        self.assertEqual(
            self.hostfiles.file_for("prod", "catalog"),
            Path("/mnt/jenkins-workspace/19/production/catalogs/test.example.com.pson.gz"),
        )
        self.assertEqual(
            self.hostfiles.file_for("prod", "errors"),
            Path("/mnt/jenkins-workspace/19/production/catalogs/test.example.com.err"),
        )
        self.assertEqual(
            self.hostfiles.file_for("change", "catalog"),
            Path("/mnt/jenkins-workspace/19/change/catalogs/test.example.com.pson.gz"),
        )
        self.assertEqual(
            self.hostfiles.file_for("change", "diff"),
            Path("/mnt/jenkins-workspace/19/diffs/test.example.com.diff"),
        )
        self.assertEqual(
            self.hostfiles.file_for("test", "diff"),
            Path("/mnt/jenkins-workspace/19/diffs/test.example.com-test.diff"),
        )
        # Now something we don't have
        self.assertRaises(ValueError, self.hostfiles.file_for, "test", "none")

    def test_outfile_for(self):
        self.assertEqual(
            self.hostfiles.outfile_for("prod", "catalog"),
            Path("/mnt/jenkins-workspace/output/1/19/test.example.com/prod.test.example.com.pson.gz"),
        )
