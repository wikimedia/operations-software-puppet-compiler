import difflib
import json


def parameters_diff(orig, other, fromfile='a', tofile='b'):
    output = "--- {f}\n+++ {t}\n\n".format(f=fromfile, t=tofile)
    old = set(orig.keys())
    new = set(other.keys())
    # Parameters only in the old definition
    only_in_old = old - new
    only_in_new = new - old
    diff = [k for k in (old & new) if orig[k] != other[k]]
    # Now calculate the string length for arrow allignment, a la puppet.
    param_len = max(map(len, (only_in_new.union(only_in_old).union(diff))))
    param_format = "{p:<%d} => {v}\n" % param_len
    for parameter in only_in_old:
        output += "-    " + param_format.format(p=parameter, v=orig[parameter])
    for parameter in only_in_new:
        output += "+    " + param_format.format(p=parameter, v=other[parameter])
    for parameter in diff:
        output += "@@\n"
        output += "-    " + param_format.format(p=parameter, v=orig[parameter])
        output += "+    " + param_format.format(p=parameter, v=other[parameter])
    return output


class PuppetResource(object):

    def __init__(self, data, resource_filter=None):
        self.resource_type = data['type']
        self.title = data['title']
        self.exported = data['exported']
        if resource_filter is None:
            self._filter = lambda x: x
        else:
            self._filter = resource_filter
        self._init_params(data.get('parameters', {}))

    def _init_params(self, kwargs):
        self.parameters = {}
        self.content = ''
        self.source = None
        # Let's first look for special
        for k, v in kwargs.items():
            if k == 'content':
                self.content = v
            else:
                self.parameters[k] = self._filter(v)

    def __str__(self):
        return "{res}[{title}]".format(res=self.resource_type,
                                       title=self.title)

    def is_same_of(self, other):
        """
        True if it designates the same resource
        """
        return (str(self) == str(other))

    def __eq__(self, other):
        if not self.is_same_of(other):
            return False
        return (self.content == other.content and
                self.source == other.source and
                self.parameters == other.parameters)

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def parse_file_content(content):
        """Parse a resource content object and return the content string.
        content objects are either a string or a hash of the form.
        content = { "__pcore_type__": "", "__pcore_value__": ""}
        """
        parsed = content
        if isinstance(content, dict):
            if content.get('__pcore_type__') == 'Binary':
                # Prefix the content so we can detect when the type changes
                parsed = 'Puppet::Pops::Types::PBinaryType::Binary\n{}'.format(
                    content.get('__pcore_value__'))
        return parsed.splitlines()

    def diff_if_present(self, other):
        if self == other:
            return None

        out = {'resource': str(self)}
        if self.content != other.content and self.resource_type == 'File':
            other_content = self.parse_file_content(other.content)
            my_content = self.parse_file_content(self.content)
            content_diff = [
                line for line in difflib.unified_diff(
                    my_content, other_content, lineterm="",
                    fromfile='{}.orig'.format(self.title),
                    tofile=self.title)
            ]
            out['content'] = "\n".join(content_diff)
        if self.parameters != other.parameters:
            out['parameters'] = parameters_diff(
                self.parameters, other.parameters,
                fromfile='{}.orig'.format(str(self)), tofile=str(self)
            )
        return out


class PuppetCatalog(object):
    def __init__(self, filename, resource_filter=None):
        self.resources = {}
        with open(filename, 'r') as fh:
            catalog = json.load(fh, 'latin_1')
        if 'data' in catalog:
            base = catalog['data']  # Puppet 3
        else:
            base = catalog  # Puppet 4 and above
        for resource in base['resources']:
            r = PuppetResource(resource, resource_filter)
            self.resources[str(r)] = r
        self.all_resources = set(self.resources.keys())
        self.name = base['name']

    def diff_if_present(self, other):
        diffs = []
        only_in_other = other.all_resources - self.all_resources
        only_in_self = self.all_resources - other.all_resources

        for resource in self.all_resources & other.all_resources:
            mine = self.resources[resource]
            theirs = other.resources[resource]
            out = mine.diff_if_present(theirs)
            if out is not None:
                diffs.append(out)

        num_changed = len(diffs)
        num_other = len(only_in_other)
        num_self = len(only_in_self)
        total_affected = (num_changed + num_other + num_self)
        num_resources = len(self.all_resources)
        perc_changed = '%.2f%%' % (100 * float(total_affected) / num_resources)
        if (total_affected) == 0:
            return None
        return {
            'total': len(self.all_resources),
            'only_in_self': only_in_self,
            'only_in_other': only_in_other,
            'resource_diffs': diffs,
            'perc_changed': perc_changed
        }
