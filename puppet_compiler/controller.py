"""This class is the main ochestration class for the puppet puppet_compiler

How data are organized:

- each job has its base directory, e.g. '/tmp/differ/2456'
- inside this directory we have the proper puppet directories, 'production'
  and 'change', and the 'diff' directory which - you guessed it - contains the
  diffs.
- Also  in the base, we have a output directory, that holds the final output for
  the user (which includes the compiled catalog, the errors and warnings, and a
  html page with some status and the diffs nicely represented, if any)
"""

import asyncio
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set, Union

import yaml

from puppet_compiler import _log, directories, nodegen, prepare, worker
from puppet_compiler.config import ControllerConfig
from puppet_compiler.presentation import html
from puppet_compiler.presentation.html import Index
from puppet_compiler.state import ChangeState, StatesCollection


class ControllerError(Exception):
    """Generic Exception for Controller Errors"""


class ControllerNoHostsError(Exception):
    """Generic Exception for Controller Errors"""


RunTaskResult = Union[Optional[worker.RunHostResult], Exception]


def with_semaphore(semaphore: asyncio.Semaphore, func: Callable):
    async def _inner(*args, **kwargs):
        async with semaphore:
            return await func(*args, **kwargs)

    return _inner


# pylint: disable=too-many-instance-attributes
class Controller:
    """Class responsible for controlling the flow of the compilation run"""

    cloud_domains = (".wmflabs", ".wikimedia.cloud")

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        configfile: Path,
        job_id: int,
        change_id: int,
        host_list: str,
        nthreads: int = 2,
        force: bool = False,
        fail_fast: bool = False,
        change_private_id: Optional[int] = None,
    ):

        # Let's first detect the installed puppet version
        self.set_puppet_version()
        configfile = Path(configfile) if isinstance(configfile, str) else configfile
        try:
            self.config = ControllerConfig.from_file(
                configfile=configfile, overrides={"pool_size": nthreads, "fail_fast": fail_fast}
            )
        except yaml.error.YAMLError as error:
            raise ControllerError from error

        self.count = 0
        self.change_id = change_id
        self.change_private_id = change_private_id
        self.hosts_raw = host_list
        self.pick_hosts(host_list)
        directories.FHS.setup(change_id, job_id, self.config.base)
        self.managecode = prepare.ManageCode(self.config, job_id, change_id, force, change_private_id)
        self.outdir = directories.FHS.output_dir
        # Set up variables to be used by the html output class
        html.change_id = change_id
        html.job_id = job_id

    @staticmethod
    def set_puppet_version() -> None:
        """Set the puppet version"""
        if not os.environ.get("PUPPET_VERSION_FULL", False):
            full = subprocess.check_output(["puppet", "--version"]).decode().rstrip()
            os.environ["PUPPET_VERSION_FULL"] = full
        if not os.environ.get("PUPPET_VERSION", False):
            major = os.environ["PUPPET_VERSION_FULL"].split(".")[0]
            os.environ["PUPPET_VERSION"] = major

    def pick_hosts(self, host_list: str) -> None:
        """Pick the set of hosts

        Arguments:
            host_list: a string representing the hosts list

        Raises:
            ControllerNoHostsError: if no hosts found

        """
        hosts = set()
        if not host_list:
            _log.info("No host list provided, generating the nodes list")
            hosts = nodegen.get_nodes(self.config)
        else:
            for host_list_part in re.split(r"\s*,\s*", host_list):
                if host_list_part.startswith("re:"):
                    host_regex = host_list_part[3:]
                    hosts.update(nodegen.get_nodes_regex(self.config, host_regex))
                elif host_list_part.startswith("O:"):
                    role = host_list_part[2:]
                    hosts.update(nodegen.get_nodes_puppetdb_class("Role::{}".format(role)))
                elif host_list_part.startswith("P:"):
                    profile = host_list_part[2:]
                    hosts.update(nodegen.get_nodes_puppetdb_class("Profile::{}".format(profile)))
                elif host_list_part.startswith("C:"):
                    puppet_class = host_list_part[2:]
                    hosts.update(nodegen.get_nodes_puppetdb_class(puppet_class))
                elif host_list_part.startswith("R:"):
                    puppet_class = host_list_part[2:]
                    hosts.update(nodegen.get_nodes_puppetdb(nodegen.capitalise_title(puppet_class)))
                elif host_list_part.startswith("cumin:"):
                    query = host_list_part[6:]
                    hosts.update(nodegen.get_nodes_cumin(query))
                elif host_list_part == "basic":
                    # Use our self as a simple wmcs host
                    hosts.add(socket.getfqdn())
                    # User one of the sretest hosts for production
                    hosts.update(nodegen.get_nodes_puppetdb_class("Profile::Sretest"))
                elif host_list_part == "auto":
                    gerrit_node_finder = nodegen.GerritNodeFinder(self.change_id, "gerrit.wikimedia.org", self.config)
                    hosts.update(gerrit_node_finder.run_hosts)
                else:
                    hosts.add(host_list_part)
        # remove empty strings added by trailing commas
        hosts.discard("")

        if not hosts:
            raise ControllerNoHostsError
        self.cloud_hosts = {h for h in hosts if h.endswith(self.cloud_domains)}
        self.prod_hosts = hosts - self.cloud_hosts

    async def run(self) -> bool:
        """Perform the compilation run.

        Returns:
            True if the run failed, False otherwise.
        """
        _log.info("Refreshing the common repos from upstream if needed")
        # If using local filesystem repositories, we need to refresh them
        # before of a run.
        _log.debug("refreshing %s", self.config.puppet_src)
        self.managecode.refresh(self.config.puppet_src)
        _log.debug("refreshing %s", self.config.puppet_private)
        self.managecode.refresh(self.config.puppet_private)
        _log.debug("refreshing %s", self.config.puppet_netbox)
        self.managecode.refresh(self.config.puppet_netbox)

        _log.info("Creating directories under %s", self.config.base)
        self.managecode.prepare()

        results = await self.run_hosts(self.prod_hosts, "production")
        results.extend(await self.run_hosts(self.cloud_hosts, "wmcs-eqiad1"))

        index = self.generate_summary(
            states_col=self.get_states(hosts=self.prod_hosts.union(self.cloud_hosts), results=results)
        )
        _log.info("Run finished; see your results at %s", index)
        # Remove the source and the diffs etc, we just need the output.
        self.managecode.cleanup()
        return self.has_failures(results)

    def index_url(self, index: Index) -> str:
        """Return the index url"""
        if self.config.http_url.startswith("/"):
            return f"{self.config.http_url}/output/{self.change_id}/{html.job_id}/{index.url}index.html"

        return f"{self.config.http_url}/{self.change_id}/{html.job_id}/{index.url}"

    async def run_hosts(self, hosts: Set[str], realm: str) -> List[RunTaskResult]:
        """Run  the compilation on a set of hosts

        Arguments:
            hosts: The hosts to run the compilation on
            realm: The realm (wmcs-eqiad1 or production) to work on

        """
        if not hosts:
            return []

        self.managecode.update_config(realm)
        _log.info("Starting run (%s)", realm)
        semaphore = asyncio.Semaphore(self.config.pool_size)
        tasks: List[asyncio.Task] = []
        for host in hosts:
            host_worker = worker.HostWorker(self.config.puppet_var, host)
            tasks.append(asyncio.create_task(with_semaphore(semaphore, host_worker.run_host)()))

        results = await self.wait_for_tasks(hosts=hosts, tasks=tasks, fail_fast=self.config.fail_fast)
        self.generate_summary(states_col=self.get_states(hosts=hosts, results=results))
        return results

    @staticmethod
    def task_failed(result: RunTaskResult) -> bool:
        return result is not None and (isinstance(result, Exception) or result.change_error or result.base_error)

    @classmethod
    def has_failures(cls, results: Iterable[RunTaskResult]) -> bool:
        return any(cls.task_failed(res) for res in results)

    async def wait_for_tasks(
        self, hosts: Iterable[str], tasks: List[asyncio.Task], fail_fast: bool = False
    ) -> List[RunTaskResult]:
        results: List[RunTaskResult] = [None] * len(tasks)

        last_results_len = len([res for res in results if res is not None])
        some_pending = True
        while some_pending:
            for index, task in enumerate(tasks):
                # give a chance to switch to another async task
                await asyncio.sleep(0.1)
                if results[index] is not None:
                    continue

                if task.done():
                    try:
                        results[index] = task.result()

                    except Exception as error:
                        results[index] = error

            some_pending = any(res is None for res in results)
            if fail_fast and self.has_failures(results):
                _log.error(
                    "A task failed, will cancel all the pending ones (--fail-fast was passed): %s",
                    next(res for res in results if self.task_failed(res)),
                )
                for task in tasks:
                    if not task.done():
                        _log.debug("Cancelling task %s", str(task))
                        task.cancel()

                return results

            cur_results_len = len([res for res in results if res is not None])
            if cur_results_len != last_results_len:
                last_results_len = cur_results_len
                self.generate_summary(states_col=self.get_states(hosts=hosts, results=results), partial=True)

        return results

    def get_states(self, hosts: Iterable[str], results: List[RunTaskResult]) -> StatesCollection:
        states_col = StatesCollection()
        completed = set()
        for result in results:
            if result is None:
                continue
            # TODO: we should catch theses earlier and create a proper RunHostResult
            if isinstance(result, Exception):
                _log.critical("Unexpected error running run_host: %s", result)
                continue
            states_col.add(self.result_to_state(hostname=result.hostname, result=result))
            completed.add(result.hostname)
        for hostname in set(hosts) - completed:
            states_col.add(self.result_to_state(hostname=hostname))
        return states_col

    def generate_summary(self, states_col: StatesCollection, partial: bool = False) -> str:
        index = Index(outdir=self.outdir, hosts_raw=self.hosts_raw)
        index.render(states_col, partial=partial)
        _log.info(
            "Index updated, you can see detailed progress for your work at %s",
            self.index_url(index),
        )
        _log.info(states_col.summary(partial=partial))
        return self.index_url(index)

    def result_to_state(self, hostname: str, result: Optional[worker.RunHostResult] = None) -> ChangeState:
        if result is None:
            # Run was cancelled, probably fail_fast, or we have not finished the run yet
            state = ChangeState(
                host=hostname,
                base_error=False,
                change_error=False,
                has_diff=False,
                has_core_diff=False,
                cancelled=True,
            )
        else:
            state = ChangeState(
                host=hostname,
                base_error=result.base_error,
                change_error=result.change_error,
                has_diff=result.has_diff,
                has_core_diff=result.has_core_diff,
                cancelled=False,
            )

        return state
