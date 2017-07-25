import copy
import json
from abc import ABCMeta, abstractmethod


class CatalogFilter(object):
    __metaclass__ = ABCMeta

    def __init__(self, filename):
        self.filename = filename
        self.original = None
        self.catalog = None
        self._filters = self.setup_filters()

    @abstractmethod
    def setup_filters(self):
        """
        Creates an array of callbacks to be used to filter the
        catalog. Each of these filters should be methods of the class
        as they'll need to access self.catalog
        """

    def run(self):
        """
        perform the filtering, write files.
        """
        self._read_json()
        self.catalog = copy.deepcopy(self.original)
        for callback in self._filters:
            callback()
        self._write_files()

    def _read_json(self):
        """
        Reads the catalog from file
        """
        with open(self.filename, 'r') as fh:
            # https://docs.puppet.com/puppet/latest/http_api/pson.html#decoding-pson-using-json-parsers
            self.original = json.load(fh, encoding='latin_1')

    def _write_files(self):
        with open(self.filename, 'w') as fh:
            json.dump(self.catalog, fh, encoding='latin_1')
        with open(self.filename + '.orig', 'w') as fh:
            json.dump(self.original, fh, encoding='latin_1')


class FilterFutureParser(CatalogFilter):
    def flatten_one_element_arrays(self):
        for resource in self.catalog['data']['resources']:
            params = resource.get('parameters', {})
            for param, val in params.items():
                if type(val) == list and len(val) == 1:
                    params[param] = val[0]

    def itos(self, value):
        if type(value) == int:
            return str(value)
        elif type(value) == list:
            return [self.itos(v) for v in value]
        elif type(value) == dict:
            return {k: self.itos(v) for k, v in value.items()}
        else:
            return value

    def cast_integers_to_string(self):
        exception_tags = set(['admin::user', 'admin::group'])
        for resource in self.catalog['data']['resources']:
            # Admin::user is a specific exception of operations/puppet
            if exception_tags & set(resource.get('tags', [])):
                continue
            params = resource.get('parameters', {})
            for param, val in params.items():
                params[param] = self.itos(val)

    def setup_filters(self):
        return [self.flatten_one_element_arrays,
                self.cast_integers_to_string]
