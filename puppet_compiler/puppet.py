"""Functions to call the puppet bunary"""
import asyncio
import os
import re
import subprocess
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Dict, List, Optional, Tuple

from puppet_compiler import _log, utils
from puppet_compiler.directories import FHS, HostFiles


class CompilationFailedError(Exception):
    """Risen when compiling a catalog fails."""

    def __init__(self, command: List[str], return_code: int):
        self.command = command
        self.return_code = return_code


def compile_cmd_env(
    hostname: str, label: str, vardir: Path, manifests_dir: Optional[Path] = None, *extra_flags
) -> Tuple[List[str], Dict[str, str]]:
    """Compaile puppet with a specific environment

    Arguments:
        hostname: The hostname to compile for
        label: indicate the environment to use (production or change)
        vardir: the puppet vardir
        manifests_dir: the location of rhte puppet manifests directory
        extra_flags: any addtinal puppet flags

    Returns:
        (cmd, env): A tuple representing the command to run and the environment
                    variables to use when running the command
    """
    env = os.environ.copy()
    if label == "prod":
        basedir = FHS.prod_dir
    else:
        basedir = FHS.change_dir

    srcdir = basedir / "src"
    privdir = basedir / "private"
    env["RUBYLIB"] = str(srcdir / "modules/wmflib/lib/")
    manifests_dir = srcdir / "manifests" if manifests_dir is None else manifests_dir
    environments_dir = srcdir / "environments"

    # factsfile will be something like
    #  "/foo/yaml/facts/production/facts/hostname.yaml
    # puppet will look for a subdir named 'facts' for
    # the yaml files, so we need to prune this path
    # accordingly.
    #
    # We can safely assume that factsfile is a valid path
    # since we would have errored out earlier if it's
    # unknown.
    factsfile = utils.facts_file(vardir, hostname)
    factpath = factsfile.parent
    yamldir = factpath.parent

    cmd = [
        "puppet",
        "catalog",
        "compile",
        "--facts_terminus=yaml",
        f"--vardir={vardir}",
        f"--modulepath={privdir / 'modules'}:{srcdir / 'modules'}:{srcdir / 'vendor_modules'}:{srcdir / 'core_modules'}",
        f"--confdir={srcdir}",
        "--color=false",
        f"--yamldir={yamldir}",
        f"--factpath={factpath}",
        f"--manifest={manifests_dir}",
        f"--environmentpath={environments_dir}",
        hostname,
    ]
    cmd.extend(extra_flags)
    return (cmd, env)


async def compile(hostname: str, label: str, vardir: Path, manifests_dir: Optional[Path] = None, *extra_flags) -> None:
    """Compile the catalog

    Arguments:
        hostname: The hostname to compile for
        label: indicate the environment to use (production or change)
        vardir: the puppet vardir
        manifests_dir: the location of rhte puppet manifests directory
        extra_flags: any addtinal puppet flags

    """
    cmd, env = compile_cmd_env(hostname, label, vardir, manifests_dir, *extra_flags)
    hostfiles = HostFiles(hostname)
    out = SpooledTemporaryFile()
    with hostfiles.file_for(label, "errors").open("w") as err:
        proc = await asyncio.subprocess.create_subprocess_shell(" ".join(cmd), stdout=out, stderr=err, env=env)
        try:
            await proc.wait()
        except asyncio.CancelledError:
            proc.kill()
            raise

    out.seek(0)
    # Puppet outputs a lot of garbage to stdout...
    with hostfiles.file_for(label, "catalog").open("wb") as f_in:
        for line in out:
            if not re.match(b"(Info|[Nn]otice|[Ww]arning)", line):
                f_in.write(line)

    if proc.returncode is not None and proc.returncode not in [0, 2]:
        raise CompilationFailedError(return_code=proc.returncode, command=cmd)


def compile_storeconfigs(
    hostname: str, vardir: Path, manifests_dir: Optional[Path] = None
) -> Tuple[bool, SpooledTemporaryFile, SpooledTemporaryFile]:
    """Specialized function to store data into puppetdb when compiling.

    Arguments:
        hostname: The hostname to compile for
        vardir: the puppet vardir
        manifests_dir: the location of rhte puppet manifests directory

    Retunrs:
        (success, out, err): tuple representing the boolean status of the command
                             and strings representing stdout and stderr
    """
    cmd, env = compile_cmd_env(
        hostname,
        "prod",
        vardir,
        manifests_dir,
        "--storeconfigs",
        "--storeconfigs_backend=puppetdb",
    )
    stdout = SpooledTemporaryFile()
    stderr = SpooledTemporaryFile()
    success = False

    try:
        subprocess.check_call(cmd, stdout=stdout, stderr=stderr, env=env)
        success = True
    except subprocess.CalledProcessError as err:
        _log.exception("Compilation failed for host %s: %s", hostname, err)

    stdout.seek(0)
    stderr.seek(0)
    return (success, stdout, stderr)


def compile_debug(hostname: str, vardir: Path) -> bool:
    """Specialized function to debug storing data into puppetdb when compiling.

    Arguments:
        hostname: The hostname to compile for
        vardir: the puppet vardir

    Retunrs:
        bool: representing the status of the command

    """
    cmd, env = compile_cmd_env(hostname, "change", vardir, None, "--debug")
    stdout = SpooledTemporaryFile()
    stderr = SpooledTemporaryFile()
    success = False

    try:
        subprocess.check_call(cmd, stdout=stdout, stderr=stderr, env=env)
        success = True
    except subprocess.CalledProcessError as err:
        _log.exception("Compilation failed for host %s: %s", hostname, err)

    stdout.seek(0)
    print("Standard Out\n{}".format("=" * 80))
    for line in stdout:
        print(line.rstrip().decode())
    stderr.seek(0)
    print("Standard Error\n{}".format("=" * 80))
    for line in stderr:
        if b"cannot collect exported resources without storeconfigs being set not" not in line:
            print(line.rstrip().decode())
    return success
