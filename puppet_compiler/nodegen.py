"""Class for generating nod lists of nodes"""
import re
from pathlib import Path
from typing import Iterable, Pattern, Set

import urllib3  # type: ignore
from cumin.query import Query  # type: ignore
from requests import get

from puppet_compiler import _log
from puppet_compiler.config import ControllerConfig

# TODO: have the CA as a config option
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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


def get_nodes_puppetdb_class(title: str) -> Set:
    """Return a set of nodes which have the class 'title' applied

    Arguments:
        title: The Class title to search for

    Returns
        set: a set of hosts to work on

    """
    title = "::".join(s.capitalize() for s in title.split("::"))
    params = {"query": '["extract",["certname","tags"]]'}
    # TODO: don't hardcode puppetdb
    puppetdb_uri = "https://localhost/pdb/query/v4/resources/Class/{}".format(title)
    nodes_json = get(puppetdb_uri, params=params, verify=False).json()
    if not nodes_json:
        _log.warning("no nodes found for class: %s", title)
        return set()
    if len(nodes_json) == 1:
        return set([nodes_json[0]["certname"]])
    # We try to reduce the set of nodes down so that we dont test nodes
    # which have the same set of classes
    # The algorithm considers a node unique if it based on the hostname
    # excluding any integers and the set of tags applied to a resource"""
    deduplicated_nodes = {}
    for node in nodes_json:
        key = "{}:{}".format(re.split(r"\d", node["certname"], 1)[0], "|".join(node["tags"]))
        if key not in deduplicated_nodes:
            deduplicated_nodes[key] = node["certname"]
    return set(deduplicated_nodes.values())


def get_nodes_cumin(query_str: str) -> Set:
    """Get a list of nodes using a raw cumin query.

    Arguments:
        query_str: The raw cumin query string

    Returns
        set: a set of hosts to work on

    """
    # Just create the config object manually so we don't have to manage a config file
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
        _log.info("testingting node:  %s", node.stem)
        yield node.stem


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
