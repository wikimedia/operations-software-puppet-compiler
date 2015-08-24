from contextlib import contextmanager
import json
import subprocess
import os
import shutil
import requests
from puppet_compiler import _log


@contextmanager
def pushd(dirname):
    cur_dir = os.getcwd()
    os.chdir(dirname)
    yield
    os.chdir(cur_dir)


class ManageCode(object):
    private_modules = ['passwords', 'contacts', 'privateexim']

    def __init__(self, config, jobid, changeid):
        self.base_dir = os.path.join(config['base'],
                                     str(jobid))
        self.puppet_src = config['puppet_src']
        self.puppet_private = config['puppet_private']
        self.puppet_var = config['puppet_var']
        self.change_id = changeid
        self.change_dir = os.path.join(self.base_dir, 'change')
        self.prod_dir = os.path.join(self.base_dir, 'production')
        self.diff_dir = os.path.join(self.base_dir, 'diffs')
        self.output_dir = os.path.join(config['base'], 'output', str(jobid))
        self.git = Git()

    def find_yaml(self, hostname):
        """ Finds facts file for the current hostname """
        facts_file = os.path.join(self.puppet_var, 'yaml', 'facts',
                                  '{}.yaml'.format(hostname))
        if os.path.isfile(facts_file):
            return facts_file
        return None

    def cleanup(self):
        """
        Remove the whole change tree.
        """
        shutil.rmtree(self.base_dir, True)

    def prepare(self):
        _log.debug("Creating directories under %s", self.base_dir)
        # Create the base directory now
        os.mkdir(self.base_dir, 0755)
        for dirname in [self.prod_dir, self.change_dir]:
            os.makedirs(os.path.join(dirname, 'catalogs'), 0755)
        os.makedirs(self.diff_dir, 0755)
        os.makedirs(self.output_dir, 0755)

        # Production
        self._prepare_dir(self.prod_dir)
        prod_src = os.path.join(self.prod_dir, 'src')
        with pushd(prod_src):
            self._copy_hiera(self.prod_dir)

        # Change
        self._prepare_dir(self.change_dir)
        change_src = os.path.join(self.change_dir, 'src')
        with pushd(change_src):
            self._fetch_change()
            # Re-do in case of hiera config changes
            self._copy_hiera(self.change_dir)

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
        with pushd(src):
            self.git.submodule('-q', 'init')
            self.git.submodule('-q', 'update')

        _log.debug('Adding symlinks')
        for module in self.private_modules:
            source = os.path.join(priv, 'modules', module)
            dst = os.path.join(src, 'modules', module)
            os.symlink(source, dst)

        shutil.copytree(os.path.join(self.puppet_var, 'ssl'),
                        os.path.join(src, 'ssl'))

    @staticmethod
    def _copy_hiera(dirname):
        """
        Copy the hiera file
        """
        hiera_file = 'modules/puppetmaster/files/production.hiera.yaml'
        priv = os.path.join(dirname, 'private')
        pub = os.path.join(dirname, 'src')
        with open(hiera_file, 'r') as g, open('hiera.yaml', 'w') as f:
            for line in g:
                l = line.replace(
                    '/etc/puppet/private', priv
                ).replace(
                    '/etc/puppet', pub)
                f.write(l)

    def _fetch_change(self):
        """get changes from the change directly"""
        git = Git()
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json; charset=UTF-8'}
        change = requests.get(
            'https://gerrit.wikimedia.org/r/changes/%d?o=CURRENT_REVISION' %
            self.change_id, headers=headers)
        change.raise_for_status()

        # Workaround the broken gerrit response...
        json_data = change.text.split("\n")[-2:][0]
        res = json.loads(json_data)
        revision = res["revisions"].values()[0]["_number"]
        ref = 'refs/changes/%02d/%d/%d' % (
            self.change_id % 100,
            self.change_id,
            revision)
        _log.debug(
            'Downloading patch for change %d, revision %d',
            self.change_id, revision)
        git.fetch('-q', 'https://gerrit.wikimedia.org/r/operations/puppet',
                  ref)
        git.cherry_pick('FETCH_HEAD')

    def _sh(command):
        try:
            subprocess.check_call(command, shell=True)
        except subprocess.CalledProcessError as e:
            _log.error("Command '%s' failed with exit code '%s'",
                       e.cmd, e.returncode)
            raise


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
        return subprocess.call(cmd)
