#!/usr/bin/env python3
import logging
import shutil
import tempfile
from argparse import ArgumentParser
from pathlib import Path

from puppet_compiler import directories, prepare, puppet, utils


def get_args() -> None:
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

    config = {
        "puppet_var": args.basedir / "puppet",
        "puppet_src": args.basedir / "production",
        "puppet_private": args.basedir / "private",
    }
    # Do the whole compilation in a dedicated directory.
    if args.build_dir:
        tmpdir = args.build_dir
    else:
        tmpdir = tempfile.mkdtemp(prefix="fill-puppetdb")
    jobid = "1"
    realm = "production" if args.host.endswith(("wmnet", "wikimedia.org")) else "labs"

    directories.FHS.setup(jobid, tmpdir)
    mangecode = prepare.ManageCode(config, jobid, args.change_id)
    if not args.build_dir:
        mangecode.base_dir.mkdir(mode=0o755)
        mangecode.change_dir.mkdir(mode=0o755, parents=True)
        (mangecode.change_dir / "catalogs").mkdir(mode=0o755, parents=True)
        mangecode._prepare_dir(mangecode.change_dir)
    srcdir = mangecode.change_dir / "src"
    with prepare.pushd(srcdir):
        if not args.build_dir:
            mangecode._fetch_change()
        mangecode._copy_hiera(mangecode.change_dir, realm)
        mangecode._create_puppetconf(mangecode.change_dir, realm)
        try:
            utils.refresh_yaml_date(utils.facts_file(config["puppet_var"], args.host))
        except utils.FactsFileNotFound as error:
            logging.error(error)
        logging.debug("%s: compiling", args.host)
        puppet.compile_debug(args.host, config["puppet_var"])
    if not args.no_clean:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
