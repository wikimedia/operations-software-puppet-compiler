import os
import shutil
import subprocess

from puppet_compiler import puppet, _log, utils
from puppet_compiler.filter import itos, flatten
from puppet_compiler.differ import PuppetCatalog
from puppet_compiler.directories import HostFiles, FHS
from puppet_compiler.presentation import html
from puppet_compiler.state import ChangeState, FutureState


def future_filter(value):
    """This filter must be used during the transition to the future parser"""
    return itos(flatten(value))


class HostWorker(object):
    E_OK = 0
    E_BASE = 1
    E_CHANGED = 2
    state = ChangeState
    html_page = html.Host
    html_index = html.Index

    def __init__(self, vardir, hostname):
        self.puppet_var = vardir
        self._files = HostFiles(hostname)
        self._envs = ['prod', 'change']
        self.hostname = hostname
        self.diffs = None
        self.resource_filter = future_filter

    def facts_file(self):
        """ Finds facts file for the current hostname """
        facts_file = utils.facts_file(self.puppet_var, self.hostname)
        if os.path.isfile(facts_file):
            return facts_file
        return None

    def run_host(self, *args, **kwdargs):
        """
        Compiles and diffs an host. Gets delegated to a worker thread
        """
        if not self.facts_file():
            _log.error('Unable to find facts for host %s, skipping',
                       self.hostname)
            return (True, True, None)
        else:
            # Refresh the facts file first
            utils.refresh_yaml_date(self.facts_file())

        errors = self._compile_all()
        if errors == self.E_OK:
            diff = self._make_diff()
        else:
            diff = None
        base = errors & self.E_BASE
        change = errors & self.E_CHANGED
        try:
            self._make_output()
            state = self.state('', self.hostname, base, change, diff)
            self._build_html(state.name)
        except Exception as e:
            _log.error('Error preparing output for %s: %s', self.hostname, e,
                       exc_info=True)
        return (base, change, diff)

    def _check_if_compiled(self, env):
        catalog = self._files.file_for(env, 'catalog')
        err = self._files.file_for(env, 'errors')
        if os.path.isfile(catalog) and os.stat(catalog).st_size > 0:
            # This is already compiled and it worked.
            return True
        if os.path.isfile(err):
            # This complied, and it just outputs an error:
            return False
        # Nothing is found
        return None

    def _compile(self, env, args):
        # this can run multiple times for the same env in different workers.
        # Check if already ran, there is no need to run a second time.
        check = self._check_if_compiled(env)
        if check is not None:
            return check
        if env != 'prod' \
           and os.path.isfile(os.path.join(FHS.change_dir, 'src', '.configs')):
            with open(os.path.join(FHS.change_dir, 'src', '.configs')) as f:
                configs = f.readlines()
            # Make sure every item has exactly 2 dashes prepended
            configs = map(lambda x: "--{}".format(x.lstrip('-')), configs)
            args.extend(configs)

        try:
            _log.info("Compiling host %s (%s)", self.hostname, env)
            puppet.compile(self.hostname,
                           env,
                           self.puppet_var,
                           *args)
        except subprocess.CalledProcessError as e:
            _log.error("Compilation failed for hostname %s "
                       " in environment %s.", self.hostname, env)
            _log.info("Compilation exited with code %d", e.returncode)
            _log.debug("Failed command: %s", e.cmd)
            return False
        else:
            return True

    def _compile_all(self):
        """
        Does the grindwork of compiling the catalogs
        """
        errors = self.E_OK
        args = []
        if not self._compile(self._envs[0], args):
            errors += self.E_BASE
        if not self._compile(self._envs[1], args):
            errors += self.E_CHANGED
        return errors

    def _make_diff(self):
        """
        Will produce diffs.

        Returns True if there are diffs, None if no diffs are found,
        False if diffing failed
        """
        _log.info("Calculating diffs for %s", self.hostname)
        try:
            original = PuppetCatalog(self._files.file_for(self._envs[0], 'catalog'),
                                     self.resource_filter)
            new = PuppetCatalog(self._files.file_for(self._envs[1], 'catalog'),
                                self.resource_filter)
            self.diffs = original.diff_if_present(new)
        except Exception as e:
            _log.error("Diffing the catalogs failed: %s", self.hostname)
            _log.info("Diffing failed with exception %s", e)
            return False
        else:
            if self.diffs is None:
                return None
            else:
                return True

    def _make_output(self):
        """
        Prepare the node output, copying the relevant files in place
        in the output directory
        """
        if not os.path.isdir(self._files.outdir):
            os.makedirs(self._files.outdir, 0o755)
        for env in self._envs:
            for label in 'catalog', 'errors':
                filename = self._files.file_for(env, label)
                if os.path.isfile(filename):
                    newname = self._files.outfile_for(env, label)
                    shutil.copy(filename, newname)

        return False

    def _build_html(self, retcode):
        """
        build the HTML output
        """
        host = self.html_page(self.hostname, self._files, retcode)
        host.htmlpage(self.diffs)


class FutureHostWorker(HostWorker):
    """
    This worker is designed to be used when transitioning to the future parser.
    It will compile the change first with the normal parser, then with the future one,
    and make a diff between the two.

    Results:
    "ok"    => both catalogs compile, and there is no diff
    "diff"  => both catalogs compile, but there is a diff
    "error" => normal parser works, but future parser doesn't
    "break" => future parser works, but the normal one doesn't
    """
    E_FUTURE = 4
    state = FutureState
    html_page = html.FutureHost
    html_index = html.FutureIndex

    def __init__(self, vardir, hostname):
        super(FutureHostWorker, self).__init__(vardir, hostname)
        self._envs = ['change', 'future']

    def _compile_all(self):
        future_args = [
            '--environment=future',
            '--parser=future',
            '--environmentpath=%s' % os.path.join(FHS.change_dir, 'src', 'environments'),
            '--default_manifest=\$confdir/manifests/site.pp'
        ]
        args = []
        errors = self.E_OK
        if not self._compile(self._envs[0], args):
            errors += self.E_BASE
        if not self._compile(self._envs[1], future_args):
            errors += self.E_CHANGED

        return errors
