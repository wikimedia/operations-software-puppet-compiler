#!/usr/bin/env python3
"""Tools for debugging the compilation run of a single host"""
import logging
import shutil
import tempfile
from argparse import ArgumentParser, Namespace
from pathlib import Path

from puppet_compiler import directories, prepare, puppet, utils
from puppet_compiler.config import ControllerConfig


def get_args() -> Namespace:
    """Get Arguments"""
    parser = ArgumentParser(
        description=(
            "Puppetdb filler - this script allows to properly populate "
            "PuppetDB with data useful for the puppet compiler"
        )
    )
    parser.add_argument(
        "--basedir",
        default="/var/lib/catalog-differ",
        type=Path,
        help="The base dir of the compiler installation",
    )
    parser.add_argument("--no-clean", action="store_true", help="dont delete the temp dir")
    parser.add_argument(
        "--build-dir",
        help="Specify a build directory, which should exist.  Otherwise use a tempdir",
        type=Path,
    )
    parser.add_argument("-c", "--change-id", type=int, help="The gerrit change number")
    parser.add_argument("host", help="The host to debug")
    return parser.parse_args()


def main() -> None:
    """Main Entry"""
    args = get_args()
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=logging.DEBUG,
        datefmt="[ %Y-%m-%dT%H:%M:%S ]",
    )

    config = ControllerConfig(
        puppet_var=args.basedir / "puppet",
        puppet_src=args.basedir / "production",
        puppet_private=args.basedir / "private",
        puppet_netbox=args.basedir / "netbox-hiera",
    )
    # Do the whole compilation in a dedicated directory.
    if args.build_dir:
        tmpdir = args.build_dir
    else:
        tmpdir = tempfile.mkdtemp(prefix="fill-puppetdb")
    jobid = 1
    realm = "production" if args.host.endswith(("wmnet", "wikimedia.org")) else "wmcs-eqiad1"

    directories.FHS.setup(args.change_id, jobid, tmpdir)
    managecode = prepare.ManageCode(config, jobid, args.change_id)
    if not args.build_dir:
        managecode.base_dir.mkdir(mode=0o755)
        managecode.change_dir.mkdir(mode=0o755, parents=True)
        (managecode.change_dir / "catalogs").mkdir(mode=0o755, parents=True)
        managecode._prepare_dir(managecode.change_dir)  # pylint: disable=protected-access
    srcdir = managecode.change_dir / "src"
    with prepare.pushd(srcdir):
        if not args.build_dir:
            managecode._fetch_change(args.change_id)  # pylint: disable=protected-access
        managecode._copy_hiera(managecode.change_dir, realm)  # pylint: disable=protected-access
        managecode._create_puppetconf(realm)  # pylint: disable=protected-access
        try:
            utils.refresh_yaml_date(utils.facts_file(config.puppet_var, args.host))
        except utils.FactsFileNotFound as error:
            logging.error(error)
        logging.debug("%s: compiling", args.host)
        puppet.compile_debug(args.host, config.puppet_var)
    if not args.no_clean:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
