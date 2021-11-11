import os
import re
import subprocess
from pathlib import Path

import yaml

from puppet_compiler import _log, directories, nodegen, prepare, threads, worker
from puppet_compiler.presentation import html
from puppet_compiler.presentation.html import Index
from puppet_compiler.state import ChangeState, StatesCollection

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


class ControllerError(Exception):
    """Generic Exception for Controller Errors"""


class ControllerNoHostsError(Exception):
    """Generic Exception for Controller Errors"""


class Controller(object):
    cloud_domains = (".wmflabs", ".wikimedia.cloud")

    def __init__(self, configfile, job_id, change_id, host_list, nthreads=2, force=False):

        # Let's first detect the installed puppet version
        configfile = Path(configfile) if isinstance(configfile, str) else configfile
        self.set_puppet_version()
        self.config = {
            # Url under which results will be found
            "http_url": "https://puppet-compiler.wmflabs.org/html",
            # Base working directory of the compiler
            "base": "/mnt/jenkins-workspace",
            # Location (either on disk, or at a remote HTTP location)
            # of the operations/puppet repository
            "puppet_src": "https://gerrit.wikimedia.org/r/operations/puppet",
            # Location (either on disk, or at a remote HTTP location)
            # of the labs/private repository
            "puppet_private": "https://gerrit.wikimedia.org/r/labs/private",
            # Directory hosting all of puppet's runtime files usually
            # under /var/lib/puppet on debian-derivatives
            "puppet_var": "/var/lib/catalog-differ/puppet",
            "pool_size": nthreads,
        }
        try:
            if configfile is not None:
                if not configfile.is_file():
                    raise ControllerError(f"Configuration file {configfile} is not a file")
                self._parse_conf(configfile)
        except yaml.error.YAMLError as error:
            _log.exception("Configuration file %s contains malformed yaml: %s", configfile, error)
            raise ControllerError from error
        except Exception:
            _log.exception("Couldn't load the configuration from %s", configfile)

        self.count = 0
        self.hosts_raw = host_list
        self.pick_hosts(host_list)
        directories.FHS.setup(job_id, self.config["base"])
        self.managecode = prepare.ManageCode(self.config, job_id, change_id, force)
        self.outdir = directories.FHS.output_dir
        # State of all nodes
        self.state = StatesCollection()
        # Set up variables to be used by the html output class
        html.change_id = change_id
        html.job_id = job_id

    def set_puppet_version(self):
        if not os.environ.get("PUPPET_VERSION_FULL", False):
            full = subprocess.check_output(["puppet", "--version"]).decode().rstrip()
            os.environ["PUPPET_VERSION_FULL"] = full
        if not os.environ.get("PUPPET_VERSION", False):
            major = os.environ["PUPPET_VERSION_FULL"].split(".")[0]
            os.environ["PUPPET_VERSION"] = major

    def pick_hosts(self, host_list):
        if not host_list:
            _log.info("No host list provided, generating the nodes list")
            hosts = nodegen.get_nodes(self.config)
        elif host_list.startswith("re:"):
            host_regex = host_list[3:]
            hosts = nodegen.get_nodes_regex(self.config, host_regex)
        elif host_list.startswith("O:"):
            role = host_list[2:]
            hosts = nodegen.get_nodes_puppetdb_class("Role::{}".format(role))
        elif host_list.startswith("P:"):
            profile = host_list[2:]
            hosts = nodegen.get_nodes_puppetdb_class("Profile::{}".format(profile))
        elif host_list.startswith("C:"):
            puppet_class = host_list[2:]
            hosts = nodegen.get_nodes_puppetdb_class(puppet_class)
        elif host_list.startswith("cumin:"):
            query = host_list[6:]
            hosts = nodegen.get_nodes_cumin(query)
        else:
            hosts = set(host for host in re.split(r"\s*,\s*", host_list) if host)

        if not hosts:
            raise ControllerNoHostsError
        self.cloud_hosts = {h for h in hosts if h.endswith(self.cloud_domains)}
        self.prod_hosts = hosts - self.cloud_hosts

    def _parse_conf(self, configfile):
        data = yaml.safe_load(configfile.read_text())
        # TODO: add data validation here
        self.config.update(data)

    def run(self) -> None:
        _log.info("Refreshing the common repos from upstream if needed")
        # If using local filesystem repositories, we need to refresh them
        # before of a run.
        if self.config["puppet_src"].startswith("/"):
            _log.debug("refreshing %s", self.config["puppet_src"])
            self.managecode.refresh(self.config["puppet_src"])
        if self.config["puppet_private"].startswith("/"):
            _log.debug("refreshing %s", self.config["puppet_private"])
            self.managecode.refresh(self.config["puppet_private"])

        _log.info("Creating directories under %s", self.config["base"])
        self.managecode.prepare()

        self._run_hosts(self.prod_hosts, "production")
        self._run_hosts(self.cloud_hosts, "labs")

        # Let's create the index
        index = Index(self.outdir, self.hosts_raw)
        index.render(self.state.states)
        _log.info("Run finished; see your results at %s", self.index_url(index))
        # Remove the source and the diffs etc, we just need the output.
        self.managecode.cleanup()

    def index_url(self, index):
        return "%s/%s/%s" % (self.config["http_url"], html.job_id, index.url)

    def _run_hosts(self, hosts, realm):
        if not hosts:
            return
        self.managecode.update_config(realm)
        # For each host, the threadpool will execute
        # Controller._run_host with the host as the only argument.
        # When this main payload is executed in a thread, the presentation
        # work is executed in the main thread via
        # Controller.on_node_compiled
        threadpool = threads.ThreadOrchestrator(self.config["pool_size"])
        _log.info("Starting run (%s)", realm)
        for host in hosts:
            host_worker = worker.HostWorker(self.config["puppet_var"], host)
            threadpool.add(
                host_worker.run_host,
                hostname=host,
            )

        # Let's wait for all runs to complete
        threadpool.fetch(self.on_node_compiled)

    def check_success(self) -> bool:
        """
        True if there are no failures
        """
        return len(self.state.states.get("fail", [])) == 0

    def on_node_compiled(self, payload):
        """
        This callback is called in the main thread once one payload has been
        completed in a worker thread.
        """
        hostname = payload.kwargs["hostname"]
        self.count += 1
        if payload.is_error:
            # Running _run_host returned with an exception, this is unexpected
            state = ChangeState(hostname=hostname, base_error=False, change_error=False, has_diff=False)
            self.state.add(state)
            _log.critical("Unexpected error running the payload: %s", payload.value)
        else:
            base_error, change_error, has_diff = payload.value
            host_state = ChangeState(
                hostname=hostname,
                base_error=base_error,
                change_error=change_error,
                has_diff=has_diff,
            )
            self.state.add(host_state)

        if not self.count % 5:
            index = Index(outdir=self.outdir, hosts_raw=self.hosts_raw)
            index.render(self.state.states)
            _log.info(
                "Index updated, you can see detailed progress for your work at %s",
                self.index_url(index),
            )
        _log.info(self.state.summary())
