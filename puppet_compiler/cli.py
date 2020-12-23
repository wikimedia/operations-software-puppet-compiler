import argparse
import logging
import os

from puppet_compiler import _log, controller


def get_args():
    """Return the parsed arguments"""
    parser = argparse.ArgumentParser(
        description="Puppet Compiler - allows to see differences in catalogs between revisions"
    )
    parser.add_argument('--debug', action='store_true', default=False, help="Print debug output")
    parser.add_argument('--force', action='store_true', default=False, help="Print debug output")
    return parser.parse_args()


change = int(os.environ.get('CHANGE'))
nodes = os.environ.get('NODES', None)
job_id = int(os.environ.get('BUILD_NUMBER'))
configfile = os.environ.get('PC_CONFIG', '/etc/puppet-compiler.conf')
nthreads = os.environ.get('NUM_THREADS', 2)
compiler_mode = os.environ.get('MODE', 'change').split(",")


def main():
    """Main entry point"""
    try:
        args = get_args()
        lvl = logging.DEBUG if args.debug else logging.INFO

        logging.basicConfig(
            format='%(asctime)s %(levelname)s: %(message)s',
            level=lvl,
            datefmt='[ %Y-%m-%dT%H:%M:%S ]'
        )
        if not change:
            _log.critical("No change provided, we cannot do anything")
            return 2
        if not job_id:
            _log.critical("No build number, are you running through jenkins?")
            return 2

        _log.info("Working on change %d", change)
        _log.info("run manually with: ./utils/pcc %d %s", change, nodes)

        try:
            c = controller.Controller(configfile, job_id, change, host_list=nodes,
                                      nthreads=nthreads, modes=compiler_mode, force=args.force)
            success = c.run()
        except controller.ControllerNoHostsError:
            _log.warning('No hosts found matching `%s` unable to do anything', nodes)
            return 2
        except controller.ControllerError:
            return 1
        # If the run is marked as failed, exit with a non-zero exit code
        if not success:
            return 1
    except Exception as e:
        _log.critical("Build run failed: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
