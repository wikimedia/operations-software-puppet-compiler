"""Module responsible for diffing puppet catalogs"""
from __future__ import annotations

import difflib
import json
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

LOGGER = getLogger(__name__)


def clone_resource(resource: PuppetResource, full_clone: bool = True) -> PuppetResource:
    """Create a copy of a resource.  If full_clone is false only copy the title,
    type and exported properties

    Paramters:
        resource: the resource to copy
        full_clone: if true clone the entire resource, if false just copy the
                    title, type and exported properties

    Returns:
        PuppetResource: a new resource object
    """
    if full_clone:
        return resource
    return PuppetResource(
        {
            "title": resource.title,
            "type": resource.resource_type,
            "exported": resource.exported,
        }
    )


def format_param(param: str, value: str, param_len: int) -> str:
    """format a parameter handeling With specific width

    Arguments:
        param: the parameter name
        value: the parameter value
        param_len: The amount of padding to use

    Return:
        str: the formated string
    """
    param_format = "{p:<%d} => {v}\n" % param_len
    return param_format.format(p=param, v=value)


def parameters_diff(orig: Dict[str, Any], other: Dict[str, Any], fromfile: str = "a", tofile: str = "b") -> str:
    """Function for diffing parameters.

    Arguments
        orig: A dictinary of the original set of parameters
        other: A dictinary of the other set of parameters
        fromfile: a strig representing the original file
        tofile: a strig representing the other file

    returns:
        str: a diff like represntation of the difference between the two blocks

    """
    output = f"--- {fromfile}\n+++ {tofile}\n\n"
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


class PuppetResource:
    """Object to manage Puppet resources"""

    def __init__(self, data: Dict):
        self.resource_type = data["type"]
        self.title = data["title"]
        self.exported = data["exported"]
        self._init_params(data.get("parameters", {}))

    def _init_params(self, kwargs: Dict):
        self.parameters = {}
        self.content = ""
        self.source = None
        # Let's first look for special
        for key, value in kwargs.items():
            if key == "content":
                self.content = value
            else:
                self.parameters[key] = value

    def __str__(self):
        return f"{self.resource_type}[{self.title}]"

    def is_same_of(self, other: Any) -> bool:
        """True if it designates the same resource."""
        return str(self) == str(other)

    def __eq__(self, other: Any) -> bool:
        if not self.is_same_of(other):
            return False
        return self.content == other.content and self.source == other.source and self.parameters == other.parameters

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    @property
    def core_type(self):
        """Indicate if the resource is a core type"""
        # The following is a list of core resources that always result in  a noop
        # as such for the purpose of pcc don't mark them as core
        core_resource_whitelist = ("Notify", "Class", "Stage")
        return "::" not in self.resource_type and self.resource_type not in core_resource_whitelist

    @staticmethod
    def parse_file_content(content: Union[str, Dict]) -> List[str]:
        """Parse a resource content object and return the content string.
        content objects are either a string or a hash of the form.
        content = { "__ptype": "", "__pvalue": ""}
        """
        if isinstance(content, dict):
            if content.get("__ptype") == "Binary":
                # Prefix the content so we can detect when the type changes
                parsed = f"Puppet::Pops::Types::PBinaryType::Binary\n{content.get('__pvalue')}"
            else:
                LOGGER.error("Unrecognized type: %s", content.get("__ptype"))
                return []
        else:
            parsed = content
        return parsed.splitlines()

    def diff_if_present(self, other: PuppetResource) -> Optional[Dict]:
        """Return the difff of two resources

        Arguments:
            other: the other resource to diff against

        Returns:
            dict: representing the difference between the two resources

        """
        if self == other:
            return None

        out = {"resource": str(self)}
        if self.content != other.content and self.resource_type in ["File", "Concat_fragment"]:
            other_content = self.parse_file_content(other.content)
            my_content = self.parse_file_content(self.content)
            out["content"] = "\n".join(
                difflib.unified_diff(
                    my_content,
                    other_content,
                    lineterm="",
                    fromfile=f"{self.title}.orig",
                    tofile=self.title,
                )
            )
        if self.parameters != other.parameters:
            out["parameters"] = parameters_diff(
                self.parameters,
                other.parameters,
                fromfile=f"{self}.orig",
                tofile=str(self),
            )
        return out


class PuppetCatalog:
    """Object for working with a  Puppet catalog"""

    def __init__(self, filename: Path) -> None:
        self.resources: Dict[str, PuppetResource] = {}
        with filename.open(encoding="latin_1") as catalog_fh:
            catalog = json.load(catalog_fh)
        for resource in catalog["resources"]:
            res = PuppetResource(resource)
            self.resources[str(res)] = res
        self.name = catalog["name"]

    @property
    def all_resources(self) -> Set:
        return set(self.resources.keys())

    @property
    def core_resources(self) -> Set:
        return {k for k, v in self.resources.items() if v.core_type}

    def diff_if_present(self, other: PuppetCatalog, core_resources: bool = False) -> Optional[Dict]:
        """Diff content if entries are present in both catalogs

        Arguments:
            other: The other puppet catalog

        Returns:
            dict: representing the differnces

        """
        return self._diff(self.all_resources & other.all_resources, other, core_resources)

    def diff_full_diff(self, other: PuppetCatalog, core_resources: bool = False) -> Optional[Dict]:
        """Diff content

        Arguments:
            other: The other puppet catalog

        Returns:
            dict: representing the differnces

        """
        return self._diff(self.all_resources | other.all_resources, other, core_resources)

    def _diff(self, resources: Set[str], other: PuppetCatalog, core_resources: bool = False) -> Optional[Dict]:
        """Produce a diff of resources only present in both catalouges

        Arguments:
            resource: The resources in this catalog
            other: The other puppet catalog

        Returns:
            dict: representing the differnces

        """
        diffs = []
        if core_resources:
            only_in_other = other.core_resources - self.core_resources
            only_in_self = self.core_resources - other.core_resources
        else:
            only_in_other = other.all_resources - self.all_resources
            only_in_self = self.all_resources - other.all_resources

        for resource in resources:
            mine = self.resources.get(resource)
            theirs = other.resources.get(resource)
            if core_resources and mine is not None and not mine.core_type:
                continue
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
        total_affected = num_changed + num_other + num_self
        num_resources = len(self.all_resources)
        if (total_affected) == 0:
            return None
        return {
            "total": num_resources,
            "only_in_self": only_in_self,
            "only_in_other": only_in_other,
            "resource_diffs": diffs,
            "perc_changed": f"{100 * float(total_affected) / num_resources:.2f}%",
        }
