"""Module for composing CLI tools"""
import asyncio
import logging
import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from puppet_compiler import _log
from puppet_compiler.controller import Controller, ControllerError, ControllerNoHostsError


def get_args() -> Namespace:
    """Return the parsed arguments.

    Returns:
        Namespace: the arguments
    """
    parser = ArgumentParser(description="Puppet Compiler - allows to see differences in catalogs between revisions")
    parser.add_argument("--debug", action="store_true", default=False, help="Print debug output")
    parser.add_argument("--force", action="store_true", default=False, help="Cleanup the outdirs if they exist.")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=bool(os.environ.get("FAIL_FAST", "")),
        help=(
            "If set, will stop running the compilations on the first host failing, set the env var FAIL_FAST to any "
            "value to set through the environment."
        ),
    )
    return parser.parse_args()


# pylint: disable=too-many-return-statements
def main() -> int:
    """Main entry point"""

    change = int(os.environ.get("CHANGE", 0))
    try:
        change_private = int(os.environ["CHANGE_PRIVATE"])
    except (KeyError, ValueError):
        change_private = None
    nodes = os.environ.get("NODES", "")
    job_id = int(os.environ.get("BUILD_NUMBER", 0))
    nthreads = int(os.environ.get("NUM_THREADS", 2))

    config_name = "puppet-compiler.conf"
    configfile = None
    # Acceptable config locations in order of precedence
    config_files = [
        # Default to a string to avoid potentially Path()-ing a None type
        Path(os.environ.get("PC_CONFIG", "")),
        Path(Path.cwd() / config_name),
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config" / config_name)),
        Path("/etc") / config_name,
    ]

    for candidate in config_files:
        if isinstance(candidate, Path) and candidate.is_file():
            configfile = candidate
            break

    if configfile is None:
        _log.error("Unable to find any config file at:")
        for file in config_files:
            _log.error(Path(file))
        return 1

    try:
        args = get_args()
        lvl = logging.DEBUG if args.debug else logging.INFO

        logging.basicConfig(
            format="%(asctime)s %(levelname)s: %(message)s",
            level=lvl,
            datefmt="[ %Y-%m-%dT%H:%M:%S ]",
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
            controller = Controller(
                Path(configfile),
                job_id,
                change,
                host_list=nodes,
                nthreads=nthreads,
                force=args.force,
                fail_fast=args.fail_fast,
                change_private_id=change_private,
            )
            run_failed = asyncio.run(controller.run())
            if run_failed:
                return 1
        except ControllerNoHostsError:
            _log.warning("No hosts found matching `%s` unable to do anything", nodes)
            return 2
        except ControllerError:
            return 1
    except Exception as err:
        _log.critical("Build run failed: %s", err, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
