import os
import re
import subprocess
import shutil
import sys
import yaml
from puppet_compiler import prepare, _log, threads, puppet, nodegen
from puppet_compiler.presentation import html
"""
How data are organized:

- each job has its base directory, e.g. '/tmp/differ/2456'
- inside this directory we have the proper puppet directories, 'production'
  and 'change', and the 'diff' directory which - you guessed it - contains the
  diffs.
- Also  in the base, we have a output directory, that holds the final output for
  the user (which includes the compiled catalog, the errors and warnings, and a
  html page with some status and the diffs nicely represented, if any)

"""


class Controller(object):

    def __init__(self, configfile, job_id, change_id, host_list=[], nthreads=2):
        self.config = {
            # Url under which results will be found
            'http_url': 'https://puppet-compiler.wmflabs.org/html',
            # Base working directory of the compiler
            'base': '/mnt/jenkins-workspace',
            # Location (either on disk, or at a remote HTTP location)
            # of the operations/puppet repository
            'puppet_src': 'https://gerrit.wikimedia.org/r/operations/puppet',
            # Location (either on disk, or at a remote HTTP location)
            # of the labs/private repository
            'puppet_private': 'https://gerrit.wikimedia.org/r/labs/private',
            # Directory hosting all of puppet's runtime files usually
            # under /var/lib/puppet on debian-derivatives
            'puppet_var': '/var/lib/catalog-differ/puppet',
            'pool_size': nthreads,
        }
        try:
            if configfile is not None:
                self._parse_conf(configfile)
        except yaml.parser.ParserError as e:
            _log.exception("Configuration file %s contains malformed yaml: %s",
                           configfile, e)
            sys.exit(2)
        except Exception:
            _log.exception("Couldn't load the configuration from %s", configfile)

        self.count = 0
        self.pick_hosts(host_list)
        self.m = prepare.ManageCode(self.config, job_id, change_id)
        self.outdir = os.path.join(self.config['base'], 'output', str(job_id))
        # State of all nodes
        self.state = {'noop': set(), 'diff': set(),
                      'err': set(), 'fail': set()}
        # Set up variables to be used by the html output class
        html.change_id = change_id
        html.job_id = job_id

    def pick_hosts(self, host_list):
        if not host_list:
            _log.info("No host list provided, generating the nodes list")
            self.hosts = nodegen.get_nodes(self.config)
        elif host_list.startswith("re:"):
            host_regex = host_list[3:]
            self.hosts = nodegen.get_nodes_regex(self.config, host_regex)
        else:
            # Standard comma-separated list of hosts
            self.hosts = re.split('\s*,\s*', host_list)

        is_labs = [host.endswith('.wmflabs') for host in self.hosts]
        if any(is_labs) and not all(is_labs):
            _log.critical("Cannot compile production and labs hosts in the "
                          "same run. Please run puppet-compiler twice.")
            sys.exit(2)
        self.realm = 'labs' if any(is_labs) else 'production'

    def _parse_conf(self, configfile):
        with open(configfile, 'r') as f:
            data = yaml.load(f)
        # TODO: add data validation here
        self.config.update(data)

    def run(self):
        _log.info("Refreshing the common repos from upstream if needed")
        # If using local filesystem repositories, we need to refresh them
        # before of a run.
        if self.config['puppet_src'].startswith('/'):
            _log.debug("refreshing %s", self.config['puppet_src'])
            self.m.refresh(self.config['puppet_src'])
        if self.config['puppet_private'].startswith('/'):
            _log.debug("refreshing %s", self.config['puppet_private'])
            self.m.refresh(self.config['puppet_private'])

        _log.info("Creating directories under %s", self.config['base'])
        self.m.prepare()

        threadpool = threads.ThreadOrchestrator(
            self.config['pool_size'])

        # For each host, the threadpool will execute
        # Controller._run_host with the host as the only argument.
        # When this main payload is executed in a thread, the presentation
        # work is executed in the main thread via
        # Controller.on_node_compiled
        for host in self.hosts:
            h = HostWorker(self.m, host, self.outdir)
            threadpool.add(h.run_host, hostname=host)
        threadpool.fetch(self.on_node_compiled)
        index = html.Index(self.outdir)
        index.render(self.state)
        _log.info('Run finished; see your results at %s/%s/', self.config['http_url'], html.job_id)
        # Remove the source and the diffs etc, we just need the output.
        self.m.cleanup()
        return self.success

    @property
    def success(self):
        """
        Try to determine if the build failed.

        Currently it just tries to see if more than half of the hosts are
        marked "fail"
        """
        if not self.count:
            # We still didn't run
            return True
        f = len(self.state['fail'])
        return (2 * f < self.count)

    def on_node_compiled(self, payload):
        """
        This callback is called in the main thread once one payload has been
        completed in a worker thread.
        """
        self.count += 1
        hostname = payload.kwargs['hostname']
        if payload.is_error:
            # Running _run_host returned with an exception, this is unexpected
            self.state['fail'].add(hostname)
            _log.critical("Unexpected error running the payload: %s",
                          payload.value)
        else:
            self.state[payload.value].add(hostname)

        if not self.count % 5:
            index = html.Index(self.outdir)
            index.render(self.state)
            _log.info('Index updated, you can see detailed progress for your work at %s', self.config['http_url'])
        _log.info(
            "Nodes: %s NOOP %s DIFF %s ERROR %s FAIL",
            len(self.state['noop']),
            len(self.state['diff']),
            len(self.state['err']),
            len(self.state['fail'])
        )


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
