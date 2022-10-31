"""Class for compiling a host"""
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from puppet_compiler import _log, puppet, utils
from puppet_compiler.differ import PuppetCatalog
from puppet_compiler.directories import HostFiles
from puppet_compiler.presentation.html import Host
from puppet_compiler.state import ChangeState


@dataclass(frozen=True)
class RunHostResult:
    base_error: bool
    change_error: bool
    has_diff: Optional[bool]


class HostWorker:
    """Class for compiling a host"""

    def __init__(self, vardir: Path, hostname: str):
        """Class for compiling a host.

        Arguments:
            vardir: The puppet var directory
            hostname: the host to work on

        """
        self.puppet_var = Path(vardir) if isinstance(vardir, str) else vardir
        self._files = HostFiles(hostname)
        self._envs = ["prod", "change"]
        self.hostname = hostname
        self.diffs: Optional[Dict] = None
        self.full_diffs: Optional[Dict] = None

    def facts_file(self) -> Path:
        """Finds facts file for the current hostname"""
        facts_file = utils.facts_file(self.puppet_var, self.hostname)
        if facts_file.is_file():
            return facts_file
        raise utils.FactsFileNotFound

    async def run_host(self, *args: List, **kwdargs: Dict) -> RunHostResult:
        """Compiles and diffs a host.

        This function gets delegated to a worker thread.
        TODO: do we need *args and *kwdargs
        """
        if not self.facts_file():
            _log.error("Unable to find facts for host %s, skipping", self.hostname)
            return RunHostResult(base_error=True, change_error=True, has_diff=None)
        # Refresh the facts file first
        try:
            utils.refresh_yaml_date(self.facts_file())
        except utils.FactsFileNotFound:
            pass

        has_diff = None
        base_error, change_error = await self._compile_all()

        if not base_error and not change_error:
            has_diff = self._make_diff()
        try:
            self._make_output()
            state = ChangeState(
                host=self.hostname,
                base_error=base_error,
                change_error=change_error,
                has_diff=has_diff,
            )
            self._build_html(state.name)
        # pylint: disable=broad-except
        except Exception as err:
            _log.exception("Error preparing output for %s: %s", self.hostname, err)
        return RunHostResult(base_error=base_error, change_error=change_error, has_diff=has_diff)

    def _check_if_compiled(self, env: str) -> Optional[bool]:
        """Check if we have allready compiled the host for a specific environment.

        Arguments:
            env: the envirnment

        Returns:
            status: True if we have allready compiled and it worked
                    False if we allready compiled and there were errors
                    NOne if we have not compiled

        """
        catalog = self._files.file_for(env, "catalog")
        err = self._files.file_for(env, "errors")
        if catalog.is_file() and catalog.stat().st_size > 0:
            # This is already compiled and it worked.
            return True
        if err.is_file():
            # This complied, and it just outputs an error:
            return False
        # Nothing is found
        return None

    async def _compile(self, env: str, args: List) -> bool:
        """Compile the host.

        This can run multiple times for the same env in different workers.
        Check if already ran, there is no need to run a second time.

        Arguments:
            env: The environment to compile for
            args: a list of addtional compile arguments

        Returns
            bool: Indicate if we successfully compiled the catalog

        """
        check = self._check_if_compiled(env)
        if check is not None:
            return check

        _log.info("Compiling host %s (%s)", self.hostname, env)
        try:
            await puppet.compile(self.hostname, env, self.puppet_var, None, *args)
        except puppet.CompilationFailedError as error:
            _log.error(
                "Compilation failed for hostname %s " " in environment %s.",
                self.hostname,
                env,
            )
            _log.info("Compilation exited with code %d", error.return_code)
            _log.debug("Failed command: %s", error.command)
            return False

        return True

    async def _compile_all(self) -> Tuple[bool, bool]:
        """Does the grindwork of compiling the catalogs.

        Returns:
            (bool,bool): An integer indicating the status base and change compile
        """
        base_error, change_error = False, False
        args: List[str] = []
        if not await self._compile(self._envs[0], args):
            base_error = True
        if not await self._compile(self._envs[1], args):
            change_error = True
        return base_error, change_error

    def _make_diff(self) -> Optional[bool]:
        """Creat the actual diff files

        Returns:
            bool: True if there are diffs
                  False if diffing failed
                  None if no diffs are found
        """
        _log.info("Calculating diffs for %s", self.hostname)
        try:
            original = PuppetCatalog(self._files.file_for(self._envs[0], "catalog"))
            new = PuppetCatalog(self._files.file_for(self._envs[1], "catalog"))
            self.diffs = original.diff_if_present(new)
            self.full_diffs = original.diff_full_diff(new)
        # pylint: disable=broad-except
        except Exception as err:
            _log.error("Diffing the catalogs failed: %s", self.hostname)
            _log.info("Diffing failed with exception %s", err)
            _log.debug(traceback.format_exc())
            return False
        else:
            if self.diffs is None:
                return None
            return True

    def _make_output(self) -> None:
        """Prepare the node output, copying the relevant files in place in the output directory"""
        if not self._files.outdir.is_dir():
            self._files.outdir.mkdir(mode=0o755, parents=True)
        for env in self._envs:
            for label in "catalog", "errors":
                filename = self._files.file_for(env, label)
                if filename.is_file():
                    newname = self._files.outfile_for(env, label)
                    shutil.copy(filename, newname)

    def _build_html(self, retcode: str) -> None:
        """Build the HTML output

        Arguments:
            retcode: A string representing the result of the compilation run
        """
        host = Host(self.hostname, self._files, retcode)
        host.htmlpage(self.diffs, self.full_diffs)
