"""Class for generating nod lists of nodes"""
import json
import re
from pathlib import Path
from typing import Iterable, Optional, Pattern, Set, Tuple

import urllib3  # type: ignore
from cumin.query import Query  # type: ignore
from requests import get

from puppet_compiler import _log
from puppet_compiler.config import ControllerConfig

# TODO: have the CA as a config option
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_type_and_title(path: Path) -> Tuple[str, Optional[str]]:
    """Open a file and determin of its type.

    return class, define, type etcs based on the resource type
    Arguments:
        path: the path to the resource file

    Returns:
        the puppet type
    """
    with path.open("r") as file_handle:
        line = file_handle.readline()
        while line:
            if line[0] == "#" or line == "\n":
                line = file_handle.readline()
                continue
            words = line.strip().split()
            puppet_type = words[0]
            title = words[1].split("(")[0]
            return puppet_type, title
    return "unknown", None


def get_nodes(config: ControllerConfig) -> Set:
    """Get all the available nodes that have separate declarations in site.pp

    Arguments:
        config: a dict representing the onfig

    Returns:
        set: A set of nodes to work on

    """
    facts_dir = config.puppet_var / "yaml"
    _log.info("Walking dir %s", facts_dir)
    site_pp = config.puppet_src / "manifests" / "site.pp"
    # Read site.pp
    node_finder = NodeFinder(site_pp)
    return node_finder.match_physical_nodes(nodelist(facts_dir))


def get_nodes_regex(config: ControllerConfig, regex: str) -> Set:
    """Get a list of nodes based on a reged

    Arguments:
        config (dict): a dictionary of app config
        regex (str): the regex to search for

    Returns
        set: a set of hosts to work on

    """
    nodes = set()
    matcher = re.compile(regex)
    facts_dir = config.puppet_var / "yaml"
    _log.info("Walking dir %s", facts_dir)
    for node in nodelist(facts_dir):
        if matcher.search(node):
            nodes.add(node)
    return nodes


def capitalise_title(title: str):
    """Function to correctly capatalise a puppet resource title.

    Arguments:
        title: the title to capatailise

    Returns:
        str: the capatilsed string
    """
    return "::".join(s.capitalize() for s in title.split("::"))


def get_nodes_puppetdb_class(title: str, deduplicate: bool = True) -> Set:
    """Get nodes for a specific class."""
    title = "Class/" + capitalise_title(title)
    return get_nodes_puppetdb(title, deduplicate)


def get_nodes_puppetdb(title: str, deduplicate: bool = True) -> Set:
    """Return a set of nodes which have the class 'title' applied

    Arguments:
        title: The Class title to search for
        deduplicate: run the de-dupo function on results

    Returns
        set: a set of hosts to work on

    """
    params = {"query": '["extract",["certname","tags"]]'}
    # TODO: don't hardcode puppetdb
    uri = "https://localhost/pdb/query/v4/resources/{}".format(title)
    nodes_json = get(uri, params=params, verify=False).json()
    if not nodes_json:
        _log.warning("no nodes found for class: %s", title)
        return set()
    if deduplicate:
        return deduplicated_nodes(nodes_json)
    return nodes_json


def deduplicated_nodes(nodes: Set):
    """De-Duplicate a set of nodes.

    We try to reduce the set of nodes down so that we dont test nodes
    which have the same set of classes
    The algorithm considers a node unique if it based on the hostname
    excluding any integers and the set of tags applied to a resource
    """

    _deduplicated_nodes = {}
    for node in nodes:
        key = "{}:{}".format(re.split(r"\d", node["certname"], 1)[0], "|".join(node["tags"]))
        if key not in _deduplicated_nodes:
            _deduplicated_nodes[key] = node["certname"]
    return set(_deduplicated_nodes.values())


def get_nodes_cumin(query_str: str) -> Set:
    """Get a list of nodes using a raw cumin query.

    Arguments:
        query_str: The raw cumin query string

    Returns
        set: a set of hosts to work on

    """
    config = {"default_backend": "puppetdb", "puppetdb": {"port": 8080, "scheme": "http"}}
    hosts = Query(config).execute(query_str)
    return set(hosts)


def nodelist(facts_dir: Path) -> Iterable[str]:
    """Return a list of nodes recursivly from a directory

    Arguments:
        facts_dir (Path): the directory to search

    Yields:
        The node name, i.e. the file path with basename with the extension removed
    """
    for node in facts_dir.glob("**/*.yaml"):
        _log.debug("testing node:  %s", node.stem)
        yield node.stem


def get_gerrit_blob(url):
    """Return a json blob from a gerrit API endpoint

    Arguments:
        url (str): gerrit url end point

    Returns
        dict: A dictionary representing the json blob returned by gerrit
    """

    _log.debug("fetch gerrit blob: %s", url)
    req = get(url, json={})
    # To prevent against Cross Site Script Inclusion (XSSI) attacks, the JSON response
    # body starts with a magic prefix line: `)]}'` that must be stripped before feeding the
    # rest of the response body to a JSON
    # https://gerrit-review.googlesource.com/Documentation/rest-api.html#output
    return json.loads(req.text.split("\n", 1)[1])


class GerritNodeFinder:
    """A Class to get a list of hosts based on files changed in the PS"""

    def __init__(self, change_number: int, gerrit_host: str, config: ControllerConfig):
        self.change_number = change_number
        self.change_url = f"https://{gerrit_host}/r/changes/{change_number}"
        self._change_data = None
        self._changed_files = None
        self._run_hosts = None
        self._config = config

    @property
    def change_data(self):
        """Property to handle fetching the change details"""
        if self._change_data is None:
            url = f"{self.change_url}?o=CURRENT_REVISION"
            self._change_data = get_gerrit_blob(url)
        return self._change_data

    @property
    def changed_files(self):
        """Property to handle fetching the changed files"""
        if self._changed_files is None:
            url = f"{self.change_url}/revisions/{self.change_data['current_revision']}/files"
            data = get_gerrit_blob(url)
            self._changed_files = [key.lstrip("/") for key in data.keys() if key != "/COMMIT_MSG"]
        return self._changed_files

    @property
    def changed_manifest_files(self):
        """Return a list of all puppet manifest files"""
        return set(changed for changed in self.changed_files if re.match(r"modules/[^\/]+/manifests", changed))

    @property
    def changed_hieradata(self):
        """return the list of change modules"""
        return set(changed for changed in self.changed_files if changed.startswith("hieradata"))

    @property
    def changed_sitepp(self):
        """returns true if the site.pp file has been updated"""
        return bool("manifests/site.pp" in self.changed_files)

    @property
    def run_hosts(self):
        """Return a unique list of hosts this change should run on"""
        if self._run_hosts is None:
            run_hosts = []
            for puppet_file in self.changed_manifest_files:
                puppet_type, title = get_type_and_title(self._config.puppet_src / puppet_file)
                if title is None:
                    continue
                _log.debug("Collecting hosts for: %s - %s", puppet_type, title)
                if puppet_type == "class":
                    run_hosts.extend(get_nodes_puppetdb_class(title, False))
                    continue
                if puppet_type == "define":
                    run_hosts.extend(get_nodes_puppetdb(capitalise_title(title), False))
            self._run_hosts = deduplicated_nodes(run_hosts)
        return self._run_hosts


# pylint: disable=too-few-public-methods
class NodeFinder:
    """Get a list of nodes based on site.pp"""

    regexp_node = re.compile(r"^node\s+/([^/]+)/")
    exact_node = re.compile(r"node\s*\'([^\']+)\'")

    def __init__(self, sitepp: Path) -> None:
        self.regexes: Set[Pattern] = set()
        self.nodes: Set[str] = set()
        for line in sitepp.read_text().splitlines():
            match = self.regexp_node.search(line)
            if match:
                _log.debug("Found regex in line %s", line.rstrip())
                self.regexes.add(re.compile(match.group(1)))
                continue
            match = self.exact_node.search(line)
            if match:
                _log.debug("Found node in line %s", line.rstrip())
                self.nodes.add(match.group(1))

    def match_physical_nodes(self, node_list: Iterable[str]) -> Set[str]:
        """Match a set of nodes against the list found locally

        Arguments:
            node_list (list): a list of nodes to search for

        Returns:
            list: a list of matching nodes
        """
        nodes: Set[str] = set()
        for node in node_list:
            discarded = None
            if node in self.nodes:
                _log.debug("Found node %s", node)
                nodes.add(node)
                self.nodes.discard(node)
                continue
            for regex in self.regexes:
                match = regex.search(node)
                if match:
                    _log.debug("Found match for node %s: %s", node, regex.pattern)
                    nodes.add(node)
                    discarded = regex
                    continue

            if discarded is not None:
                self.regexes.discard(discarded)

        return nodes
