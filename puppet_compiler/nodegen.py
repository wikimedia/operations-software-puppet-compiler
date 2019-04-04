import re
import os
from puppet_compiler import _log


def get_nodes(config):
    """
    Get all the available nodes that have separate declarations in site.pp
    """
    facts_dir = os.path.join(config['puppet_var'], 'yaml', 'facts')
    _log.info("Walking dir %s", facts_dir)
    site_pp = os.path.join(config['puppet_src'], 'manifests', 'site.pp')
    # Read site.pp
    with open(site_pp, 'r') as sitepp:
        n = NodeFinder(sitepp)
    return n.match_physical_nodes(nodelist(facts_dir))


def get_nodes_regex(config, regex):
    nodes = []
    r = re.compile(regex)
    facts_dir = os.path.join(config['puppet_var'], 'yaml', 'facts')
    _log.info("Walking dir %s", facts_dir)
    for node in nodelist(facts_dir):
        if r.search(node):
            nodes.append(node)
    return nodes


def nodelist(facts_dir):
    for subdir in os.walk(facts_dir):
        for node in subdir[2]:
            yield node.replace('.yaml', '')


class NodeFinder(object):
    regexp_node = re.compile(r'^node\s+/([^/]+)/')
    exact_node = re.compile(r"node\s*\'([^\']+)\'")

    def __init__(self, sitepp):
        self.regexes = set()
        self.nodes = set()
        for line in sitepp.readlines():
            m = self.regexp_node.search(line)
            if m:
                _log.debug('Found regex in line %s', line.rstrip())
                self.regexes.add(re.compile(m.group(1)))
                continue
            m = self.exact_node.search(line)
            if m:
                _log.debug('Found node in line %s', line.rstrip())
                self.nodes.add(m.group(1))

    def match_physical_nodes(self, nodelist):
        nodes = []
        for node in nodelist:
            discarded = None
            if node in self.nodes:
                _log.debug('Found node %s', node)
                nodes.append(node)
                self.nodes.discard(node)
                continue
            for regex in self.regexes:
                # TODO: this may be very slow, should calculate this
                m = regex.search(node)
                if m:
                    _log.debug('Found match for node %s: %s', node,
                               regex.pattern)
                    nodes.append(node)
                    discarded = regex
                    continue

            if discarded is not None:
                self.regexes.discard(discarded)

        return nodes
