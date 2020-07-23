import difflib
import io  # TODO: remove after dropping python2.7
import json


def clone_resource(resource, full_clone=True):
    """Create a copy of a resource.  If full_clone is false only copy the title,
    type and exported properties

    Paramters:
        resource (PuppetResource): the resource to copy
        full_clone (bool): if true clone the entire resource, if false just copy the
                           title, type and exported properties

    Returns:
        PuppetResource: a new resource object
    """
    if full_clone:
        return resource
    return PuppetResource({
        'title': resource.title,
        'type': resource.resource_type,
        'exported': resource.exported,
    })


def format_param(param, value, param_len):
    """format a parameter handeling none ascii characters"""
    param_format = "{p:<%d} => {v}\n" % param_len
    try:
        return param_format.format(p=param, v=value)
    except UnicodeEncodeError:
        return param_format.format(p=param, v=value.encode('latin1'))


def parameters_diff(orig, other, fromfile='a', tofile='b'):
    """Function for diffing parameters"""
    output = "--- {f}\n+++ {t}\n\n".format(f=fromfile, t=tofile)
    old = set(orig.keys())
    new = set(other.keys())
    # Parameters only in the old definition
    only_in_old = old - new
    only_in_new = new - old
    diff = [k for k in (old & new) if orig[k] != other[k]]
    # Now calculate the string length for arrow allignment, a la puppet.
    param_len = max(map(len, (only_in_new.union(only_in_old).union(diff))))
    # need to do the encoding because of pson
    # https://puppet.com/docs/puppet/5.5/http_api/pson.html
    for parameter in only_in_old:
        output += "-    " + format_param(parameter, orig[parameter], param_len)
    for parameter in only_in_new:
        output += "+    " + format_param(parameter, other[parameter], param_len)
    for parameter in diff:
        output += "@@\n"
        output += "-    " + format_param(parameter, orig[parameter], param_len)
        output += "+    " + format_param(parameter, other[parameter], param_len)
    return output


class PuppetResource(object):
    """Object to manage Puppet resources"""

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
        return str(self) == str(other)

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
    """Object for working with a  Puppet catalog"""
    def __init__(self, filename, resource_filter=None):
        self.resources = {}
        with io.open(filename, 'r', encoding='latin_1') as catalog_fh:
            catalog = json.load(catalog_fh)
        if 'data' in catalog:
            base = catalog['data']  # Puppet 3
        else:
            base = catalog  # Puppet 4 and above
        for resource in base['resources']:
            res = PuppetResource(resource, resource_filter)
            self.resources[str(res)] = res
        self.all_resources = set(self.resources.keys())
        self.name = base['name']

    def diff_if_present(self, other):
        return self._diff(self.all_resources & other.all_resources, other)

    def diff_full_diff(self, other):
        return self._diff(self.all_resources | other.all_resources, other)

    def _diff(self, resources, other):
        """Produce a diff of resources only present in both catalouges"""
        diffs = []
        only_in_other = other.all_resources - self.all_resources
        only_in_self = self.all_resources - other.all_resources

        for resource in resources:
            mine = self.resources.get(resource)
            theirs = other.resources.get(resource)
            # if we don't have a resource in both create an empty one for diffing purposes
            if mine is None:
                mine = clone_resource(other.resources[resource], False)
            if theirs is None:
                theirs = clone_resource(self.resources[resource], False)
            out = mine.diff_if_present(theirs)
            if out is not None:
                diffs.append(out)

        num_changed = len(diffs)
        num_other = len(only_in_other)
        num_self = len(only_in_self)
        total_affected = (num_changed + num_other + num_self)
        num_resources = len(self.all_resources)
        if (total_affected) == 0:
            return None
        return {
            'total': num_resources,
            'only_in_self': only_in_self,
            'only_in_other': only_in_other,
            'resource_diffs': diffs,
            'perc_changed': '%.2f%%' % (100 * float(total_affected) / num_resources)
        }
