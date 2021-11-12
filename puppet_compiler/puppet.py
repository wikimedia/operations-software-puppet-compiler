"""Functions to call the puppet bunary"""
import os
import re
import subprocess
from tempfile import SpooledTemporaryFile

from puppet_compiler import _log, utils
from puppet_compiler.directories import FHS, HostFiles


def compile_cmd_env(hostname, label, vardir, manifests_dir=None, *extra_flags):
    """Compaile puppet with a specific environment"""
    env = os.environ.copy()
    if label == "prod":
        basedir = FHS.prod_dir
    else:
        basedir = FHS.change_dir

    srcdir = basedir / "src"
    privdir = basedir / "private"
    env["RUBYLIB"] = srcdir / "modules/wmflib/lib/"
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
    yamldir = factsfile.parent.parent

    cmd = [
        "puppet",
        "master",
        f"--vardir={vardir}",
        f"--modulepath={privdir / 'modules'}:{srcdir / 'modules'}",
        f"--confdir={srcdir}",
        f"--compile={hostname}",
        "--color=false",
        f"--yamldir={yamldir}",
        f"--manifest={manifests_dir}",
        f"--environmentpath={environments_dir}",
    ]
    cmd.extend(extra_flags)
    return (cmd, env)


def compile(hostname, label, vardir, manifests_dir=None, *extra_flags):
    """
    Compile the catalog
    """
    cmd, env = compile_cmd_env(hostname, label, vardir, manifests_dir, *extra_flags)
    hostfiles = HostFiles(hostname)

    with hostfiles.file_for(label, "errors").open("w") as err:
        out = SpooledTemporaryFile()
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)

    # Puppet outputs a lot of garbage to stdout...
    with hostfiles.file_for(label, "catalog").open("wb") as f:
        out.seek(0)
        for line in out:
            if not re.match(b"(Info|[Nn]otice|[Ww]arning)", line):
                f.write(line)


def compile_storeconfigs(hostname, vardir, manifests_dir=None):
    """
    Specialized function to store data into puppetdb
    when compiling.
    """
    cmd, env = compile_cmd_env(
        hostname, "prod", vardir, manifests_dir, "--storeconfigs", "--storeconfigs_backend=puppetdb"
    )
    out = SpooledTemporaryFile()
    err = SpooledTemporaryFile()
    success = False

    try:
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)
        success = True
    except subprocess.CalledProcessError as e:
        _log.exception("Compilation failed for host %s: %s", hostname, e)

    out.seek(0)
    err.seek(0)
    return (success, out, err)


def compile_debug(hostname, vardir):
    """
    Specialized function to store data into puppetdb
    when compiling.
    """
    cmd, env = compile_cmd_env(hostname, "change", vardir, None, "-d")
    out = SpooledTemporaryFile()
    err = SpooledTemporaryFile()
    success = False

    try:
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)
        success = True
    except subprocess.CalledProcessError as e:
        _log.exception("Compilation failed for host %s: %s", hostname, e)

    out.seek(0)
    print("Standard Out\n{}".format("=" * 80))
    for line in out:
        print(line.strip())
    err.seek(0)
    print("Standard Error\n{}".format("=" * 80))
    for line in err:
        if b"cannot collect exported resources without storeconfigs being set not" not in line:
            print(line.decode().strip())
    return success
