import re

from cumin.query import Query
from requests import get

from puppet_compiler import _log


def get_nodes(config):
    """
    Get all the available nodes that have separate declarations in site.pp
    """
    facts_dir = config["puppet_var"] / "yaml"
    _log.info("Walking dir %s", facts_dir)
    site_pp = config["puppet_src"] / "manifests" / "site.pp"
    # Read site.pp
    with open(site_pp, "r") as sitepp:
        n = NodeFinder(sitepp)
    return n.match_physical_nodes(nodelist(facts_dir))


def get_nodes_regex(config, regex):
    nodes = set()
    r = re.compile(regex)
    facts_dir = config["puppet_var"] / "yaml"
    _log.info("Walking dir %s", facts_dir)
    for node in nodelist(facts_dir):
        if r.search(node):
            nodes.add(node)
    return nodes


def get_nodes_puppetdb_class(title):
    """return a set of nodes which have the class 'title' applied"""
    title = "::".join(s.capitalize() for s in title.split("::"))
    params = {"query": '["extract",["certname","tags"]]'}
    puppetdb_uri = "http://localhost:8080/pdb/query/v4/resources/Class/{}".format(title)
    nodes_json = get(puppetdb_uri, params=params).json()
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


def get_nodes_cumin(query_str):
    """get a list of nodes using a raw cumin query"""
    # Just create the config object manually so we don't have to manage a config file
    config = {"default_backend": "puppetdb", "puppetdb": {"port": 8080, "scheme": "http"}}
    hosts = Query(config).execute(query_str)
    return set(hosts)


def nodelist(facts_dir):
    for node in facts_dir.glob("**/*.yaml"):
        _log.info("testingting node:  %s", node.stem)
        yield node.stem


class NodeFinder(object):
    regexp_node = re.compile(r"^node\s+/([^/]+)/")
    exact_node = re.compile(r"node\s*\'([^\']+)\'")

    def __init__(self, sitepp):
        self.regexes = set()
        self.nodes = set()
        for line in sitepp.readlines():
            m = self.regexp_node.search(line)
            if m:
                _log.debug("Found regex in line %s", line.rstrip())
                self.regexes.add(re.compile(m.group(1)))
                continue
            m = self.exact_node.search(line)
            if m:
                _log.debug("Found node in line %s", line.rstrip())
                self.nodes.add(m.group(1))

    def match_physical_nodes(self, nodelist):
        nodes = set()
        for node in nodelist:
            discarded = None
            if node in self.nodes:
                _log.debug("Found node %s", node)
                nodes.add(node)
                self.nodes.discard(node)
                continue
            for regex in self.regexes:
                # TODO: this may be very slow, should calculate this
                m = regex.search(node)
                if m:
                    _log.debug("Found match for node %s: %s", node, regex.pattern)
                    nodes.add(node)
                    discarded = regex
                    continue

            if discarded is not None:
                self.regexes.discard(discarded)

        return nodes
