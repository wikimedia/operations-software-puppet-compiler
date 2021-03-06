from contextlib import contextmanager
import json
import subprocess
import os
import shutil
import requests
from puppet_compiler import _log
from puppet_compiler.directories import FHS

LDAP_YAML_PATH = '/etc/ldap.yaml'


@contextmanager
def pushd(dirname):
    cur_dir = os.getcwd()
    os.chdir(dirname)
    yield
    os.chdir(cur_dir)


class ManageCode(object):
    private_modules = ['passwords', 'contacts', 'privateexim']

    def __init__(self, config, jobid, changeid, realm='production', force=False):
        self.base_dir = FHS.base_dir
        self.puppet_src = config['puppet_src']
        self.puppet_private = config['puppet_private']
        self.puppet_var = config['puppet_var']
        self.change_id = changeid
        self.realm = realm
        self.force = force

        self.change_dir = FHS.change_dir
        self.prod_dir = FHS.prod_dir
        self.diff_dir = FHS.diff_dir
        self.output_dir = FHS.output_dir
        self.git = Git()

    def cleanup(self):
        """
        Remove the whole change tree.
        """
        shutil.rmtree(self.base_dir, True)

    def prepare(self):
        _log.debug("Creating directories under %s", self.base_dir)
        # Create the base directory now
        if self.force:
            # This is manly used during development where you dont care about the output
            # and are running the same command over and over with the same job_id
            _log.debug('removing old directories, [%s, %s]', self.base_dir, self.output_dir)
            self.cleanup()
            shutil.rmtree(self.output_dir, True)
        os.mkdir(self.base_dir, 0o755)
        for dirname in [self.prod_dir, self.change_dir]:
            os.makedirs(os.path.join(dirname, 'catalogs'), 0o755)
        os.makedirs(self.diff_dir, 0o755)
        os.makedirs(self.output_dir, 0o755)

        # Production
        self._prepare_dir(self.prod_dir)
        prod_src = os.path.join(self.prod_dir, 'src')
        with pushd(prod_src):
            self._copy_hiera(self.prod_dir, self.realm)
            self._create_puppetconf(self.change_dir, self.realm)

        # Change
        self._prepare_dir(self.change_dir)
        change_src = os.path.join(self.change_dir, 'src')
        with pushd(change_src):
            self._fetch_change()
            # Re-do in case of hiera config changes
            self._copy_hiera(self.change_dir, self.realm)
            self._create_puppetconf(self.change_dir, self.realm)

    def refresh(self, gitdir):
        """
        Refresh a git repository
        """
        with pushd(gitdir):
            self.git.pull('-q', '--rebase')

    # Private methods
    def _prepare_dir(self, dirname):
        """
        prepare a specific directory to compile puppet
        """
        _log.debug("Cloning directories...")
        src = os.path.join(dirname, 'src')
        self.git.clone('-q', self.puppet_src, src)
        priv = os.path.join(dirname, 'private')
        self.git.clone('-q', self.puppet_private, priv)

        _log.debug('Adding symlinks')
        for module in self.private_modules:
            source = os.path.join(priv, 'modules', module)
            dst = os.path.join(src, 'modules', module)
            os.symlink(source, dst)

        shutil.copytree(os.path.join(self.puppet_var, 'ssl'),
                        os.path.join(src, 'ssl'))
        # Puppetdb-related configs
        puppetdb_conf = os.path.join(self.puppet_var, 'puppetdb.conf')
        if os.path.isfile(puppetdb_conf):
            _log.debug('Copying the puppetdb config file')
            shutil.copy(
                puppetdb_conf,
                os.path.join(src, 'puppetdb.conf')
            )
        routes_conf = os.path.join(self.puppet_var, 'routes.yaml')
        if os.path.isfile(routes_conf):
            _log.debug('Copying the routes file')
            shutil.copy(routes_conf, os.path.join(src, 'routes.yaml'))

    @staticmethod
    def _copy_hiera(dirname, realm):
        """
        Copy the hiera file
        """
        hiera_file = 'modules/puppetmaster/files/{realm}.hiera.yaml'.format(
            realm=realm
        )
        priv = os.path.join(dirname, 'private')
        pub = os.path.join(dirname, 'src')
        with open(hiera_file, 'r') as g, open('hiera.yaml', 'w') as f:
            for line in g:
                data = line.replace(
                    '/etc/puppet/private', priv
                ).replace(
                    '/etc/puppet', pub)
                f.write(data)

    @staticmethod
    def _create_puppetconf(dirname, realm):
        if realm != 'labs':
            _log.debug('Realm is %s, skipping writing puppet.conf', realm)
            return

        template = """# This file has been generated by puppet-compiler.
[master]
    node_terminus = exec
    external_nodes = /usr/local/bin/puppet-enc
"""

        with open('puppet.conf', 'w') as f:
            f.write(template)
        _log.debug('Wrote puppet.conf with puppet-enc settings')

    def _fetch_change(self):
        """get changes from the change directly"""
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json; charset=UTF-8'}
        change = requests.get(
            'https://gerrit.wikimedia.org/r/changes/%d?o=CURRENT_REVISION' %
            self.change_id, headers=headers)
        change.raise_for_status()

        # Workaround the broken gerrit response...
        json_data = change.text.split("\n")[-2:][0]
        res = json.loads(json_data)
        revision = list(res["revisions"].values())[0]["_number"]
        project = res["project"]
        ref = 'refs/changes/%02d/%d/%d' % (
            self.change_id % 100,
            self.change_id,
            revision)
        _log.debug(
            'Downloading patch for project %s, change %d, revision %d',
            project, self.change_id, revision)

        # Assumption:
        # Gerrit suported repo names and branches:
        # operations/puppet - origin/production
        if project == 'operations/puppet':
            self._checkout_gerrit_revision(project, ref)
            self._pull_rebase_origin('production')
        else:
            raise RuntimeError("Unsupported Gerrit project: " + project)

    def _checkout_gerrit_revision(self, project, revision):
        self.git.fetch(
            '-q', 'https://gerrit.wikimedia.org/r/' + project, revision)
        self.git.checkout('FETCH_HEAD')

    def _pull_rebase_origin(self, origin_branch):
        self.git.pull('--rebase', 'origin', origin_branch)


class Git():
    '''
    This class is not strictly needed. It's just a container for the member
    functions, so that they are not in the global namespace. There is no point
    in instantiating it ever.

    Partly salvaged from utils/new_wmf_service
    '''

    def __getattr__(self, action):
        action = action.replace('_', '-')

        def git_exec(*args, **kwdargs):
            return self._execute_command(action, *args)
        return git_exec

    def _execute_command(self, command, *args):
        cmd = ['git', command]
        cmd.extend(args)
        try:
            return subprocess.check_call(cmd)
        except subprocess.CalledProcessError as error:
            _log.critical('`{}` failed: {}'.format(' '.join(cmd), error))
            raise SystemExit(2)
