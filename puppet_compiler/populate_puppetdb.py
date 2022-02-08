#!/usr/bin/python3
"""Tool used to populate the puppetdb with some node data"""

import logging
import shutil
import tempfile
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from puppet_compiler import config, directories, nodegen, prepare, puppet, utils


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
    parser.add_argument("--debug", action="store_true", default=False, help="Print debug output")
    parser.add_argument("--host", help="if present only populate the DB for this host")
    return parser.parse_args()


def populate_node(node: str, cfg: config.ControllerConfig, debug: bool) -> None:
    """Populate puppetdb for this specific node

    Arguments:
        node: The node to work on
        config: a dictionary representing the config
        debug: if to enable debug output

    """
    print("=" * 80)
    print("Compiling catalog for {}".format(node))

    try:
        utils.refresh_yaml_date(utils.facts_file(cfg.puppet_var, node))
    except utils.FactsFileNotFound as error:
        print("ERROR: {}".format(error))
        return
    succ, out, err = puppet.compile_storeconfigs(node, cfg.puppet_var)
    if succ:
        print("OK")
    else:
        for line in err:
            print(line)
        if debug:
            for line in out:
                print(line)


def setup_environment(tmpdir, cfg: config.ControllerConfig, jobid: int = 1) -> prepare.ManageCode:
    """Setup the temporary directory structure.

    Arguments:
        config: a dictionary representing the config
        jobid: the jobid number to use

    Returns
         srcdir: The path to the created src directory

    """
    directories.FHS.setup(jobid, tmpdir)
    managecode = prepare.ManageCode(cfg, jobid, 1)
    managecode.base_dir.mkdir(mode=0o755)
    managecode.prod_dir.mkdir(mode=0o755, parents=True)
    managecode._prepare_dir(managecode.prod_dir)  # pylint: disable=protected-access
    routes = {"master": {"facts": {"terminus": "yaml", "cache": "yaml"}}}
    (managecode.prod_dir / "src" / "routes.yaml").write_text(yaml.dump(routes))
    return managecode


def main():
    """main entry"""
    args = get_args()
    if args.debug:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=lvl,
        datefmt="[ %Y-%m-%dT%H:%M:%S ]",
    )

    cfg = config.ControllerConfig(
        puppet_var=args.basedir / "puppet",
        puppet_src=args.basedir / "production",
        puppet_private=args.basedir / "private",
    )
    tmpdir = tempfile.mkdtemp(prefix="fill-puppetdb")
    managecode = setup_environment(tmpdir, cfg)
    # Do the whole compilation in a dedicated directory.
    nodes = set([args.host]) if args.host else nodegen.get_nodes(cfg)
    cloud_nodes = set(n for n in nodes if n.endswith(("wikimedia.cloud", "wmflabs")))
    prod_nodes = nodes - cloud_nodes
    with prepare.pushd(managecode.prod_dir / "src"):
        print(f"{30 * '#'} working on {len(prod_nodes)} prod nodes {30 * '#'}")
        managecode._copy_hiera(managecode.prod_dir, "production")  # pylint: disable=protected-access
        for node in prod_nodes:
            populate_node(node, cfg, args.debug)
        print(f"{30 * '#'} working on {len(cloud_nodes)} cloud nodes {30 * '#'}")
        managecode._copy_hiera(managecode.prod_dir, "labs")  # pylint: disable=protected-access
        for node in cloud_nodes:
            populate_node(node, cfg, args.debug)
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
