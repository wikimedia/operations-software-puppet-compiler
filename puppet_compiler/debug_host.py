#!/usr/bin/env python3
import logging
import os
import shutil
import tempfile

from argparse import ArgumentParser

from puppet_compiler import directories, prepare, puppet, utils


def get_args():
    parser = ArgumentParser(
        description="Puppetdb filler - this script allows to properly populate PuppetDB with data useful for the puppet compiler"
    )
    parser.add_argument(
        '--basedir',
        default='/var/lib/catalog-differ',
        help='The base dir of the compiler installation',
    )
    parser.add_argument(
        '--no-clean', action='store_true', help='dont delete the temp dir'
    )
    parser.add_argument('--build-dir', help='dont create a temp dir')
    parser.add_argument('-c', '--change-id', type=int, help='The gerrit change number')
    parser.add_argument('host', help='The host to debug')
    return parser.parse_args()


def main():
    args = get_args()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=logging.DEBUG,
        datefmt='[ %Y-%m-%dT%H:%M:%S ]',
    )

    config = {
        'puppet_var': os.path.join(args.basedir, 'puppet'),
        'puppet_src': os.path.join(args.basedir, 'production'),
        'puppet_private': os.path.join(args.basedir, 'private'),
    }
    # Do the whole compilation in a dedicated directory.
    if args.build_dir:
        tmpdir = args.build_dir
    else:
        tmpdir = tempfile.mkdtemp(prefix='fill-puppetdb')
    jobid = '1'
    directories.FHS.setup(jobid, tmpdir)
    realm = 'production' if args.host.endswith(('wmnet', 'wikimedia.org')) else 'labs'
    m = prepare.ManageCode(config, jobid, args.change_id, realm)
    if not args.build_dir:
        os.mkdir(m.base_dir, 0o755)
        os.makedirs(m.change_dir, 0o755)
        os.makedirs(os.path.join(m.change_dir, 'catalogs'), 0o755)
        m._prepare_dir(m.change_dir)
    srcdir = os.path.join(m.change_dir, 'src')
    with prepare.pushd(srcdir):
        if not args.build_dir:
            m._fetch_change()
        m._copy_hiera(m.change_dir, realm)
        try:
            utils.refresh_yaml_date(utils.facts_file(config['puppet_var'], args.host))
        except utils.FactsFileNotFound as error:
            logging.error(error)
        logging.debug('%s: compiling', args.host)
        puppet.compile_debug(args.host, config['puppet_var'])
    if not args.no_clean:
        shutil.rmtree(tmpdir)


if __name__ == '__main__':
    main()
