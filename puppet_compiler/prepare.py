"""Pepare the enironment"""
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import requests

from puppet_compiler import _log
from puppet_compiler.config import ControllerConfig
from puppet_compiler.directories import FHS

LDAP_YAML_PATH = "/etc/ldap.yaml"


@contextmanager
def pushd(dirname: Path):
    """Context manager to change pwd

    Arguments:
        dirname: The directory to change to

    """
    cur_dir = Path.cwd()
    os.chdir(dirname)
    yield
    os.chdir(cur_dir)


# pylint: disable=too-many-instance-attributes
class ManageCode:
    """Class tp prepare code directories"""

    private_modules = ["passwords", "contacts", "privateexim"]

    def __init__(
        self, config: ControllerConfig, jobid: int, changeid: int, force=False, change_private_id: Optional[int] = None
    ):
        # TODO: jobid is unused
        self.jobid = jobid
        self.base_dir = FHS.base_dir
        self.puppet_src = config.puppet_src
        self.puppet_private = config.puppet_private
        self.puppet_netbox = config.puppet_netbox
        self.puppet_var = config.puppet_var
        self.change_id = changeid
        self.change_private_id = change_private_id
        self.force = force
        self.storeconfigs = config.storeconfigs

        self.change_dir = FHS.change_dir
        self.prod_dir = FHS.prod_dir
        self.diff_dir = FHS.diff_dir
        self.output_dir = FHS.output_dir
        self.git = Git()

    def cleanup(self) -> None:
        """Remove the whole change tree."""
        shutil.rmtree(self.base_dir, True)

    def prepare(self) -> None:
        """Prepare the directories"""
        _log.debug("Creating directories under %s %s", self.base_dir, self.force)
        # Create the base directory now
        if self.force:
            # This is manly used during development where you dont care about the output
            # and are running the same command over and over with the same job_id
            _log.debug("removing old directories, [%s, %s]", self.base_dir, self.output_dir)
            self.cleanup()
            shutil.rmtree(self.output_dir, True)
        self.base_dir.mkdir(mode=0o755)
        for dirname in [self.prod_dir, self.change_dir]:
            (dirname / "catalogs").mkdir(mode=0o755, parents=True)
        self.diff_dir.mkdir(mode=0o755, parents=True)
        self.output_dir.mkdir(mode=0o755, parents=True)

        # Production
        self._prepare_dir(self.prod_dir)
        self._prepare_dir(self.change_dir)
        change_src = self.change_dir / "src"
        with pushd(change_src):
            self._fetch_change(self.change_id)
        if self.change_private_id is not None:
            with pushd(self.prod_dir / "private"):
                self._fetch_change(self.change_private_id)
            with pushd(self.change_dir / "private"):
                self._fetch_change(self.change_private_id)

    def update_config(self, realm: str) -> None:
        """update hiera and puppet config files

        Arguments:
            realm: the realm to change to

        """
        prod_src = self.prod_dir / "src"
        with pushd(prod_src):
            self._copy_hiera(self.prod_dir, realm)
            self._create_puppetconf(realm, self.storeconfigs)

        change_src = self.change_dir / "src"
        with pushd(change_src):
            self._copy_hiera(self.change_dir, realm)
            self._create_puppetconf(realm, self.storeconfigs)

    def refresh(self, gitdir: Path) -> None:
        """Refresh a git repository.

        Arguments:
            gitdir: the directory to refresh

        """
        with pushd(gitdir):
            self.git.pull("-q", "--rebase")

    # Private methods
    def _prepare_dir(self, dirname: Path) -> None:
        """Prepare a specific directory to compile puppet.

        Arguments
            dirname: the directory to prepare

        """
        _log.debug("Cloning directories...")
        src = dirname / "src"
        self.git.clone("-q", str(self.puppet_src), str(src))
        priv = dirname / "private"
        self.git.clone("-q", str(self.puppet_private), str(priv))
        netbox = dirname / "netbox-hiera"
        self.git.clone("-q", str(self.puppet_netbox), str(netbox))

        _log.debug("Adding symlinks")
        for module in self.private_modules:
            source = priv / "modules" / module
            dst = src / "modules" / module
            dst.symlink_to(source)

        shutil.copytree(self.puppet_var / "ssl", src / "ssl")
        # Puppetdb-related configs
        puppetdb_conf = self.puppet_var / "puppetdb.conf"
        if puppetdb_conf.is_file():
            _log.debug("Copying the puppetdb config file")
            shutil.copy(puppetdb_conf, src / "puppetdb.conf")
        routes_conf = self.puppet_var / "routes.yaml"
        if routes_conf.is_file():
            _log.debug("Copying the routes file")
            shutil.copy(routes_conf, src / "routes.yaml")

    @staticmethod
    def _copy_hiera(dirname: Path, realm: str) -> None:
        """Copy the realm specific hiera file to dirname.

        Arguments:
            dirname: the directory to copy to
            realm: The realm to use

        """
        hiera_file = Path(f"modules/puppetmaster/files/hiera/{realm}.yaml")

        priv = dirname / "private"
        netbox = dirname / "netbox-hiera"
        pub = dirname / "src"
        with hiera_file.open() as f_in, Path("hiera.yaml").open("w") as f_out:
            for line in f_in:
                data = (
                    line.replace("/etc/puppet/private", str(priv))
                    .replace("/etc/puppet/netbox", str(netbox))
                    .replace("/etc/puppet", str(pub))
                )
                f_out.write(data)

    @staticmethod
    def _create_puppetconf(realm: str, storeconfigs: bool = True) -> None:
        """Copy the realm specific puppet conf file to dirname.

        Arguments:
            realm: The realm to use
            storeconfigs: Use puppetdb

        """
        if realm == "wmcs-eqiad1":
            config = """# This file has been generated by puppet-compiler.
[master]
    node_terminus = exec
    external_nodes = /usr/local/bin/puppet-enc
"""
        elif storeconfigs:
            config = """# This file has been generated by puppet-compiler.
[master]
storeconfigs = true
storeconfigs_backend = puppetdb
"""
        else:
            config = """# This file has been generated by puppet-compiler.
[master]
"""

        Path("puppet.conf").write_text(config)
        _log.debug("Wrote puppet.conf with puppet-enc settings")

    def _fetch_change(self, change_id: int) -> None:
        """get changes from the change directly"""
        headers = {"Accept": "application/json", "Content-Type": "application/json; charset=UTF-8"}
        change = requests.get(
            "https://gerrit.wikimedia.org/r/changes/%d?o=CURRENT_REVISION" % change_id, headers=headers
        )
        change.raise_for_status()

        # Workaround the broken gerrit response...
        json_data = change.text.split("\n")[-2:][0]
        res = json.loads(json_data)
        revision = list(res["revisions"].values())[0]["_number"]
        project = res["project"]
        ref = "refs/changes/%02d/%d/%d" % (change_id % 100, change_id, revision)
        _log.debug("Downloading patch for project %s, change %d, revision %d", project, change_id, revision)

        # Assumption:
        # Gerrit suported repo names and branches:
        # operations/puppet - origin/production
        if project == "operations/puppet":
            self._checkout_gerrit_revision(project, ref)
            self._pull_rebase_origin("production")
        elif project == "labs/private":
            self._checkout_gerrit_revision(project, ref)
            self._pull_rebase_origin("master")
        else:
            raise RuntimeError("Unsupported Gerrit project: " + project)

    def _checkout_gerrit_revision(self, project: str, revision: str) -> None:
        self.git.fetch("-q", f"https://gerrit.wikimedia.org/r/{project}", revision)
        self.git.checkout("-B", revision, "FETCH_HEAD")
        self.git.log("--oneline", "-n1")

    def _pull_rebase_origin(self, origin_branch: str) -> None:
        self.git.pull("--rebase", "origin", origin_branch)


# pylint: disable=too-few-public-methods
class Git:
    """
    This class is not strictly needed. It's just a container for the member
    functions, so that they are not in the global namespace. There is no point
    in instantiating it ever.

    Partly salvaged from utils/new_wmf_service
    """

    def __getattr__(self, action):
        action = action.replace("_", "-")

        def git_exec(*args):
            """Executes a git command and returns the output"""
            return self._execute_command(action, *args)

        return git_exec

    @staticmethod
    def _execute_command(command: str, *args):
        cmd = ["git", command]
        cmd.extend(args)
        try:
            return subprocess.check_call(cmd)
        except subprocess.CalledProcessError as error:
            _log.critical("`%s` failed: %s", " ".join(cmd), error)
            raise SystemExit(2) from error
