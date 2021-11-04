#!/usr/bin/python3

import argparse
import logging
import os
import shutil
import tempfile

from puppet_compiler import directories, nodegen, prepare, puppet, utils


def get_args():
    """Get Arguments"""
    parser = argparse.ArgumentParser(
        description=(
            "Puppetdb filler - this script allows to properly populate "
            "PuppetDB with data useful for the puppet compiler"
        )
    )
    parser.add_argument(
        "--basedir",
        default="/var/lib/catalog-differ",
        help="The base dir of the compiler installation",
    )
    parser.add_argument("--debug", action="store_true", default=False, help="Print debug output")
    parser.add_argument("--host", help="if present only populate the DB for this host")
    return parser.parse_args()


def populate_node(node, config):
    """populate puppetdb for this specific node"""
    print("=" * 80)
    print("Compiling catalog for {}".format(node))

    try:
        utils.refresh_yaml_date(utils.facts_file(config["puppet_var"], node))
    except utils.FactsFileNotFound as error:
        print("ERROR: {}".format(error))
        return
    for manifest_dir in ["/dev/null", None]:
        print("manifest_dir: {}".format(manifest_dir))
        succ, _, err = puppet.compile_storeconfigs(node, config["puppet_var"], manifest_dir)
        if succ:
            print("OK")
        else:
            for line in err:
                print(line)


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

    config = {
        "puppet_var": os.path.join(args.basedir, "puppet"),
        "puppet_src": os.path.join(args.basedir, "production"),
        "puppet_private": os.path.join(args.basedir, "private"),
    }
    # Do the whole compilation in a dedicated directory.
    tmpdir = tempfile.mkdtemp(prefix="fill-puppetdb")
    jobid = "1"
    directories.FHS.setup(jobid, tmpdir)
    managecode = prepare.ManageCode(config, jobid, None)
    os.mkdir(managecode.base_dir, 0o755)
    os.makedirs(managecode.prod_dir, 0o755)
    managecode._prepare_dir(managecode.prod_dir)
    srcdir = os.path.join(managecode.prod_dir, "src")
    nodes = set([args.host]) if args.host else nodegen.get_nodes(config)
    cloud_nodes = set(n for n in nodes if n.endswith(("wikimedia.cloud", "wmflabs")))
    prod_nodes = nodes - cloud_nodes
    with prepare.pushd(srcdir):
        print(f"{30 * '#'} working on {len(prod_nodes)} prod nodes {30 * '#'}")
        managecode._copy_hiera(managecode.prod_dir, "production")
        for node in prod_nodes:
            populate_node(node, config)
        print(f"{30 * '#'} working on {len(cloud_nodes)} cloud nodes {30 * '#'}")
        managecode._copy_hiera(managecode.prod_dir, "labs")
        for node in cloud_nodes:
            populate_node(node, config)
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
