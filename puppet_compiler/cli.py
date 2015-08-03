import argparse
import logging
import os
import sys
import re
from puppet_compiler import _log, controller

parser = argparse.ArgumentParser(
    description="Puppet Compiler - allows to see differences in catalogs between revisions"
)
parser.add_argument('--debug', action='store_true', default=False, help="Print debug output")

change = int(os.environ.get('CHANGE'))
nodes = os.environ.get('NODES', [])
job_id = int(os.environ.get('BUILD_NUMBER'))
configfile = os.environ.get('PC_CONFIG', '/etc/puppet-compiler.conf')
if nodes:
    nodes = re.split('\s*,\s*', nodes)


def main():
    try:
        opts = parser.parse_args()
        if opts.debug:
            lvl = logging.DEBUG
        else:
            lvl = logging.INFO

            logging.basicConfig(
                format='%(asctime)s %(levelname)s: %(message)s',
                level=lvl,
                datefmt='[ %Y-%m-%dT%H:%M:%S ]'
            )
        if not change:
            _log.critical("No change provided, we cannot do anything")
            sys.exit(2)
        if not job_id:
            _log.critical("No build number, are you running through jenkins?")
            sys.exit(2)

        _log.info("Working on change %d", change)
        c = controller.Controller(configfile, job_id,
                                  change, nodes)
        success = c.run()
        # If the run is marked as failed, exit with a non-zero exit code
        if not success:
            sys.exit(1)
    except Exception as e:
        _log.critical("Build run failed: %s", e, exc_info=True)
        sys.exit(1)
