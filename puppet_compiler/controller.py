import re
import sys

import yaml

from collections import defaultdict

from puppet_compiler import directories, _log, nodegen, prepare, state, \
    threads, worker
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
        self.run_modes = {'change': worker.HostWorker}
        try:
            if configfile is not None:
                self._parse_conf(configfile)
        except yaml.parser.ParserError as e:
            _log.exception("Configuration file %s contains malformed yaml: %s",
                           configfile, e)
            sys.exit(2)
        except Exception:
            _log.exception("Couldn't load the configuration from %s", configfile)

        self.count = defaultdict(int)
        self.pick_hosts(host_list)
        directories.FHS.setup(job_id, self.config['base'])
        self.m = prepare.ManageCode(self.config, job_id, change_id)
        self.outdir = directories.FHS.output_dir
        # State of all nodes
        self.state = state.StatesCollection()
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
            for mode, worker_class in self.run_modes.items():
                state_class = worker_class.state
                html_class = worker_class.html_index
                h = worker_class(self.config['puppet_var'], host)
                threadpool.add(h.run_host,
                               hostname=host,
                               mode=mode,
                               classes=(state_class, html_class))
        threadpool.fetch(self.on_node_compiled)
        for mode in self.run_modes.keys():
            index = html_class(self.outdir, mode)
            index.render(self.state.modes[mode])
        _log.info('Run finished; see your results at %s', self.index_url(index))
        # Remove the source and the diffs etc, we just need the output.
        self.m.cleanup()
        return self.success

    def index_url(self, index):
        return "%s/%s/%s" % (self.config['http_url'], html.job_id, index.url)

    @property
    def success(self):
        """
        Try to determine if the build failed.

        Currently it just tries to see if more than half of the hosts are
        marked "fail"
        """
        for mode in self.run_modes.keys():
            if not self.count[mode]:
                # We still didn't run
                continue
            try:
                f = len(self.state.modes[mode]['fail'])
            except KeyError:
                continue
            if (2 * f >= self.count[mode]):
                return False
        return True

    def on_node_compiled(self, payload):
        """
        This callback is called in the main thread once one payload has been
        completed in a worker thread.
        """
        hostname = payload.kwargs['hostname']
        state_class, html_class = payload.kwargs['classes']
        mode = payload.kwargs['mode']
        self.count[mode] += 1
        if payload.is_error:
            # Running _run_host returned with an exception, this is unexpected
            state = state_class(mode, hostname, False, False, False)
            self.state.add(state)
            _log.critical("Unexpected error running the payload: %s",
                          payload.value)
        else:
            base, change, diff = payload.value
            host_state = state_class(mode, hostname, base, change, diff)
            self.state.add(host_state)

        if not self.count[mode] % 5:
            index = html_class(self.outdir, mode=mode)
            index.render(self.state.modes[mode])
            _log.info('Index updated, you can see detailed progress for your work at %s', self.index_url(index))
        _log.info(self.state.mode_to_str(mode))
