import copy
import io  # TODO: remove after dropping python2.7
import json
import os
import shutil
import tempfile
import unittest

from puppet_compiler.filter import FilterFutureParser


catalog = {'data': {
    'resources': [
        {
            "title": "main",
            "parameters": {
                'testlist': ["a"],
                'testtruelist': [1, 2, 3],
                'hash': {"a": 1, "b": "test"},
            },
        },
        {
            "title": "main2",
            "parameters": {
                'testtruelist': [1, 2, 3],
            },
            "tags": ["admin::user", "admin"]
        }

    ]
}}


class TestFilter(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix='puppet-compiler')
        self.catalog = os.path.join(self.tempdir, 'catalog')
        with io.open(self.catalog, 'w', encoding='latin_1') as fh:
            fh.write(u'{}'.format(json.dumps(catalog)))

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_init(self):
        f = FilterFutureParser(self.catalog)
        assert f.original is None
        assert f.catalog is None
        assert f.filename == self.catalog
        assert f._filters == [
            f.flatten_one_element_arrays,
            f.cast_integers_to_string
        ]

    def test_read_json(self):
        f = FilterFutureParser(self.catalog)
        f._read_json()
        assert f.original == catalog

    def test_write_files(self):
        f = FilterFutureParser(self.catalog)
        f._read_json()
        f.catalog = f.original
        f._write_files()
        with open(self.catalog, 'r') as fh:
            self.assertEqual(catalog, json.load(fh))
        with open(self.catalog + '.orig', 'r') as fh:
            self.assertEqual(catalog, json.load(fh))

    def test_itos(self):
        f = FilterFutureParser(self.catalog)
        assert f.itos(1) == "1"
        assert f.itos(['', 2, 00]) == ['', '2', '0']
        self.assertEqual(f.itos(catalog['data']['resources'][0]['parameters']['testtruelist']), ['1', '2', '3'])

    def test_filtering(self):
        self.maxDiff = None
        f = FilterFutureParser(self.catalog)
        f.run()
        filtered_catalog = copy.deepcopy(catalog)
        params = filtered_catalog['data']['resources'][0]['parameters']
        params['testlist'] = "a"
        params['testtruelist'] = ['1', '2', '3']
        params['hash'] = {"a": '1', "b": "test"}

        with io.open(self.catalog, 'r', encoding='latin_1') as fh:
            self.assertEqual(filtered_catalog, json.load(fh))
        with io.open(self.catalog + '.orig', 'r', encoding='latin_1') as fh:
            self.assertEqual(catalog, json.load(fh))
