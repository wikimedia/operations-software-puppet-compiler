import os
import re
import shutil
import subprocess

from puppet_compiler import puppet, _log
from puppet_compiler.presentation import html


class HostWorker(object):
    E_OK = 0
    E_PROD = 1
    E_CHANGE = 2

    def __init__(self, manager, hostname, outdir):
        self.m = manager
        self.files = {
            'prod': {
                'catalog': os.path.join(self.m.prod_dir, 'catalogs',
                                        hostname + '.pson'),
                'errors': os.path.join(self.m.prod_dir, 'catalogs',
                                       hostname + '.err')
            },
            'change': {
                'catalog': os.path.join(self.m.change_dir, 'catalogs',
                                        hostname + '.pson'),
                'errors': os.path.join(self.m.change_dir, 'catalogs',
                                       hostname + '.err')
            }
        }
        self.hostname = hostname
        self.outdir = os.path.join(outdir, self.hostname)

    def run_host(self, *args, **kwdargs):
        """
        Compiles and diffs an host. Gets delegated to a worker thread
        """
        if not self.m.find_yaml(self.hostname):
            _log.error('Unable to find facts for host %s, skipping',
                       self.hostname)
            return 'fail'
        errors = self._compile_all()
        retcode = self._make_diff(errors)
        try:
            self._make_output()
            self._build_html(retcode)
        except Exception as e:
            _log.error('Error preparing output for %s: %s', self.hostname, e,
                       exc_info=True)
        return retcode

    def _compile_all(self):
        """
        Does the grindwork of compiling the catalogs
        """
        errors = self.E_OK
        try:
            _log.info("Compiling host %s (production)", self.hostname)
            puppet.compile(self.hostname,
                           self.m.prod_dir,
                           self.m.puppet_var)
        except subprocess.CalledProcessError as e:
            _log.error("Compilation failed for hostname %s "
                       " with the current tree.", self.hostname)
            _log.info("Compilation exited with code %d", e.returncode)
            _log.debug("Failed command: %s", e.cmd)
            errors += self.E_PROD
        args = []
        if os.path.isfile(os.path.join(self.m.change_dir, 'src', '.configs')):
            with open(os.path.join(self.m.change_dir, 'src', '.configs')) as f:
                configs = f.readlines()
                # Make sure every item has exactly 2 dashes prepended
                configs = map(lambda x: "--{}".format(x.lstrip('-')), configs)
                args.extend(configs)
        try:
            _log.info("Compiling host %s (change)", self.hostname)
            puppet.compile(self.hostname,
                           self.m.change_dir,
                           self.m.puppet_var,
                           *args)
        except subprocess.CalledProcessError as e:
            _log.error("Compilation failed for hostname %s "
                       " with the change.", self.hostname)
            _log.info("Compilation exited with code %d", e.returncode)
            _log.debug("Failed command: %s", e.cmd)
            errors += self.E_CHANGE
        # Now test for regressions with the future parser
        return errors

    def _make_diff(self, errors):
        """
        Based on the outcome of compilation, will or will not produce diffs
        """
        if errors == self.E_OK:
            # Both nodes compiled correctly
            _log.info("Calculating diffs for %s", self.hostname)
            try:
                puppet.diff(self.m.base_dir, self.hostname)
            except subprocess.CalledProcessError as e:
                _log.error("Diffing the catalogs failed: %s", self.hostname)
                _log.info("Diffing exited with code %d", e.returncode)
                _log.debug("Failed command: %s", e.cmd)
                return 'fail'
            else:
                if self._get_diff():
                    return 'diff'
                else:
                    return 'noop'
        elif errors == self.E_PROD:
            # Production didn't compile, the changed tree did.
            # Declare this a success
            return 'noop'
        elif errors == self.E_CHANGE:
            # Ouch, the change didn't work
            return 'err'
        else:
            # This is most probably the compiler's fault,
            # let's call this a fail
            return 'fail'

    def _make_output(self):
        """
        Prepare the node output, copying the relevant files in place
        in the output directory
        """
        os.makedirs(self.outdir, 0755)
        for env in self.files:
            for label in 'catalog', 'errors':
                filename = self.files[env][label]
                if os.path.isfile(filename):
                    name = os.path.basename(filename)
                    newname = os.path.join(self.outdir, env + '.' + name)
                    shutil.copy(filename, newname)

        diff = self._get_diff()
        if diff:
            shutil.copy(diff, self.outdir)
            return True

        return False

    def _get_diff(self):
        """
        Get diffs name if the file exists
        """
        diff = os.path.join(self.m.diff_dir, self.hostname + '.diff')
        if os.path.isfile(diff) and os.path.getsize(diff) > 0:
            with open(diff, 'r') as f:
                for line in f:
                    # If no changes were detected, puppet catalog diff outputs
                    # a line with 'fqdn     0.0%'
                    # we use that to detect a noop change since we have no other
                    # means to detect that.
                    if re.match('^{}\s+0.0\%'.format(self.hostname), line):
                        return False
            return diff
        return False

    def _build_html(self, retcode):
        """
        build the HTML output
        """
        # TODO: implement the actual html parsing
        host = html.Host(self.hostname, self.m.diff_dir, self.outdir, retcode)
        host.htmlpage(self.files)
